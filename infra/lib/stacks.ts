import {
  CfnOutput,
  Duration,
  RemovalPolicy,
  Stack,
  StackProps,
  Tags,
} from "aws-cdk-lib";
import { Construct } from "constructs";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as ecs from "aws-cdk-lib/aws-ecs";
import * as ecr from "aws-cdk-lib/aws-ecr";
import * as elb from "aws-cdk-lib/aws-elasticloadbalancingv2";
import * as acm from "aws-cdk-lib/aws-certificatemanager";
import * as rds from "aws-cdk-lib/aws-rds";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as sqs from "aws-cdk-lib/aws-sqs";
import * as sns from "aws-cdk-lib/aws-sns";
import * as subscriptions from "aws-cdk-lib/aws-sns-subscriptions";
import * as secrets from "aws-cdk-lib/aws-secretsmanager";
import * as kms from "aws-cdk-lib/aws-kms";
import * as cognito from "aws-cdk-lib/aws-cognito";
import * as iam from "aws-cdk-lib/aws-iam";
import * as logs from "aws-cdk-lib/aws-logs";
import * as cloudwatch from "aws-cdk-lib/aws-cloudwatch";
import * as actions from "aws-cdk-lib/aws-cloudwatch-actions";
import * as budgets from "aws-cdk-lib/aws-budgets";
import * as ses from "aws-cdk-lib/aws-ses";
import * as scheduler from "aws-cdk-lib/aws-scheduler";
import * as cloudfront from "aws-cdk-lib/aws-cloudfront";
import * as origins from "aws-cdk-lib/aws-cloudfront-origins";
import { ipGateway } from "./ip-gateway";

export class Foundation extends Stack {
  readonly vpc: ec2.Vpc;
  readonly db: rds.DatabaseInstance;
  readonly bucket: s3.Bucket;
  readonly queue: sqs.Queue;
  readonly eventQueue: sqs.Queue;
  readonly cluster: ecs.Cluster;
  readonly apiRepo: ecr.Repository;
  readonly webRepo: ecr.Repository;
  readonly key: kms.Key;
  readonly sessionSecret: secrets.Secret;
  readonly pool: cognito.UserPool;
  readonly client: cognito.UserPoolClient;
  readonly alerts: sns.Topic;
  readonly appSg: ec2.SecurityGroup;
  readonly emailEvents: sns.Topic;
  constructor(scope: Construct, id: string, props: StackProps) {
    super(scope, id, props);
    Tags.of(this).add("Project", "talyn");
    Tags.of(this).add("Environment", "development");
    this.vpc = new ec2.Vpc(this, "Network", {
      maxAzs: 2,
      natGateways: 0,
      subnetConfiguration: [
        { name: "app-public", subnetType: ec2.SubnetType.PUBLIC, cidrMask: 24 },
        {
          name: "database-isolated",
          subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
          cidrMask: 24,
        },
      ],
    });
    this.vpc.addGatewayEndpoint("S3Endpoint", {
      service: ec2.GatewayVpcEndpointAwsService.S3,
    });
    this.key = new kms.Key(this, "DataKey", {
      enableKeyRotation: true,
      removalPolicy: RemovalPolicy.RETAIN,
      description: "Talyn application data encryption",
    });
    this.bucket = new s3.Bucket(this, "PrivateMedia", {
      encryption: s3.BucketEncryption.KMS,
      encryptionKey: this.key,
      bucketKeyEnabled: true,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      versioned: true,
      removalPolicy: RemovalPolicy.RETAIN,
      objectOwnership: s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
      lifecycleRules: [
        {
          id: "incomplete-uploads",
          abortIncompleteMultipartUploadAfter: Duration.days(1),
        },
        {
          id: "version-backstop",
          noncurrentVersionExpiration: Duration.days(30),
        },
      ],
    });
    this.appSg = new ec2.SecurityGroup(this, "ApplicationSecurity", {
      vpc: this.vpc,
      description: "Only Talyn ALB can reach runtime containers",
    });
    const dbSg = new ec2.SecurityGroup(this, "DatabaseSecurity", {
      vpc: this.vpc,
      allowAllOutbound: false,
    });
    dbSg.addIngressRule(
      this.appSg,
      ec2.Port.tcp(5432),
      "Talyn runtime database TLS",
    );
    const pgParams = new rds.ParameterGroup(this, "DatabaseParameters", {
      engine: rds.DatabaseInstanceEngine.postgres({
        version: rds.PostgresEngineVersion.VER_16,
      }),
      parameters: {
        "rds.force_ssl": "1",
        log_statement: "none",
        log_min_error_statement: "panic",
      },
    });
    this.db = new rds.DatabaseInstance(this, "Database", {
      vpc: this.vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      securityGroups: [dbSg],
      engine: rds.DatabaseInstanceEngine.postgres({
        version: rds.PostgresEngineVersion.VER_16,
      }),
      instanceType: ec2.InstanceType.of(
        ec2.InstanceClass.T4G,
        ec2.InstanceSize.MICRO,
      ),
      credentials: rds.Credentials.fromGeneratedSecret("talyn", {
        encryptionKey: this.key,
      }),
      databaseName: "talyn",
      parameterGroup: pgParams,
      allocatedStorage: 20,
      maxAllocatedStorage: 30,
      storageType: rds.StorageType.GP3,
      storageEncrypted: true,
      storageEncryptionKey: this.key,
      multiAz: false,
      publiclyAccessible: false,
      backupRetention: Duration.days(7),
      deleteAutomatedBackups: false,
      deletionProtection: true,
      removalPolicy: RemovalPolicy.SNAPSHOT,
      autoMinorVersionUpgrade: true,
    });
    this.sessionSecret = new secrets.Secret(this, "SessionSecret", {
      encryptionKey: this.key,
      generateSecretString: { passwordLength: 64, excludePunctuation: true },
      removalPolicy: RemovalPolicy.RETAIN,
    });
    const dead = new sqs.Queue(this, "JobDeadLetters", {
      encryption: sqs.QueueEncryption.KMS,
      encryptionMasterKey: this.key,
      retentionPeriod: Duration.days(14),
      enforceSSL: true,
    });
    this.queue = new sqs.Queue(this, "Jobs", {
      encryption: sqs.QueueEncryption.KMS,
      encryptionMasterKey: this.key,
      visibilityTimeout: Duration.minutes(5),
      retentionPeriod: Duration.days(4),
      deadLetterQueue: { queue: dead, maxReceiveCount: 5 },
      enforceSSL: true,
    });
    this.eventQueue = new sqs.Queue(this, "EmailEventsQueue", {
      encryption: sqs.QueueEncryption.KMS,
      encryptionMasterKey: this.key,
      retentionPeriod: Duration.days(4),
      deadLetterQueue: { queue: dead, maxReceiveCount: 5 },
      enforceSSL: true,
    });
    this.emailEvents = new sns.Topic(this, "EmailEventsTopic", {
      masterKey: this.key,
    });
    this.emailEvents.addSubscription(
      new subscriptions.SqsSubscription(this.eventQueue),
    );
    this.key.addToResourcePolicy(
      new iam.PolicyStatement({
        principals: [
          new iam.ServicePrincipal("ses.amazonaws.com"),
          new iam.ServicePrincipal("sns.amazonaws.com"),
          new iam.ServicePrincipal("budgets.amazonaws.com"),
        ],
        actions: ["kms:GenerateDataKey", "kms:Decrypt"],
        resources: ["*"],
        conditions: { StringEquals: { "aws:SourceAccount": this.account } },
      }),
    );
    this.emailEvents.addToResourcePolicy(
      new iam.PolicyStatement({
        principals: [new iam.ServicePrincipal("ses.amazonaws.com")],
        actions: ["sns:Publish"],
        resources: [this.emailEvents.topicArn],
        conditions: { StringEquals: { "AWS:SourceAccount": this.account } },
      }),
    );
    this.pool = new cognito.UserPool(this, "Managers", {
      selfSignUpEnabled: true,
      signInAliases: { email: true },
      autoVerify: { email: true },
      standardAttributes: { email: { required: true, mutable: false } },
      passwordPolicy: {
        minLength: 12,
        requireDigits: true,
        requireLowercase: true,
        requireUppercase: true,
        requireSymbols: true,
      },
      accountRecovery: cognito.AccountRecovery.EMAIL_ONLY,
      removalPolicy: RemovalPolicy.RETAIN,
    });
    this.client = this.pool.addClient("WebClient", {
      generateSecret: false,
      authFlows: { userPassword: true },
      preventUserExistenceErrors: true,
      accessTokenValidity: Duration.hours(1),
      idTokenValidity: Duration.hours(1),
      refreshTokenValidity: Duration.days(1),
    });
    this.apiRepo = new ecr.Repository(this, "ApiRepository", {
      repositoryName: "talyn-api",
      imageScanOnPush: true,
      imageTagMutability: ecr.TagMutability.IMMUTABLE,
      removalPolicy: RemovalPolicy.RETAIN,
      lifecycleRules: [{ maxImageCount: 15 }],
    });
    this.webRepo = new ecr.Repository(this, "WebRepository", {
      repositoryName: "talyn-web",
      imageScanOnPush: true,
      imageTagMutability: ecr.TagMutability.IMMUTABLE,
      removalPolicy: RemovalPolicy.RETAIN,
      lifecycleRules: [{ maxImageCount: 15 }],
    });
    this.cluster = new ecs.Cluster(this, "Cluster", {
      vpc: this.vpc,
      clusterName: "talyn-development",
    });
    this.alerts = new sns.Topic(this, "OperationalAlerts");
    this.alerts.addToResourcePolicy(
      new iam.PolicyStatement({
        principals: [new iam.ServicePrincipal("budgets.amazonaws.com")],
        actions: ["sns:Publish"],
        resources: [this.alerts.topicArn],
        conditions: { StringEquals: { "aws:SourceAccount": this.account } },
      }),
    );
    const alertEmail = this.node.tryGetContext("alertEmail");
    if (alertEmail)
      this.alerts.addSubscription(
        new subscriptions.EmailSubscription(alertEmail),
      );
    new budgets.CfnBudget(this, "MonthlyBudget", {
      budget: {
        budgetName: "talyn-development",
        budgetType: "COST",
        timeUnit: "MONTHLY",
        budgetLimit: {
          amount: Number(this.node.tryGetContext("monthlyBudget") || 150),
          unit: "USD",
        },
        costFilters: { TagKeyValue: ["user:Project$talyn"] },
      },
      notificationsWithSubscribers: [50, 80, 100].map((threshold) => ({
        notification: {
          comparisonOperator: "GREATER_THAN",
          notificationType: "ACTUAL",
          threshold,
          thresholdType: "PERCENTAGE",
        },
        subscribers: [
          { subscriptionType: "SNS", address: this.alerts.topicArn },
        ],
      })),
    });
    const dlqAlarm = new cloudwatch.Alarm(this, "DeadLettersAlarm", {
      metric: dead.metricApproximateNumberOfMessagesVisible(),
      threshold: 1,
      evaluationPeriods: 1,
      comparisonOperator:
        cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
    });
    dlqAlarm.addAlarmAction(new actions.SnsAction(this.alerts));
    const storageAlarm = new cloudwatch.Alarm(this, "DatabaseStorageAlarm", {
      metric: this.db.metricFreeStorageSpace(),
      threshold: 3 * 1024 ** 3,
      evaluationPeriods: 2,
      comparisonOperator: cloudwatch.ComparisonOperator.LESS_THAN_THRESHOLD,
    });
    storageAlarm.addAlarmAction(new actions.SnsAction(this.alerts));
    const providerArn = this.node.tryGetContext("githubOidcProviderArn");
    const provider = providerArn
      ? iam.OpenIdConnectProvider.fromOpenIdConnectProviderArn(
          this,
          "ExistingGithubOidc",
          providerArn,
        )
      : new iam.OpenIdConnectProvider(this, "GithubOidc", {
          url: "https://token.actions.githubusercontent.com",
          clientIds: ["sts.amazonaws.com"],
        });
    const repo =
      this.node.tryGetContext("githubRepository") || "r1cksync/Talyn";
    // New GitHub repositories use immutable owner/repository IDs in the subject.
    const subjectPrefix =
      this.node.tryGetContext("githubSubjectPrefix") || `repo:${repo}`;
    const deployRole = new iam.Role(this, "GithubDeploymentRole", {
      roleName: "talyn-github-deploy",
      assumedBy: new iam.WebIdentityPrincipal(
        provider.openIdConnectProviderArn,
        {
          StringEquals: {
            "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
            "token.actions.githubusercontent.com:sub": `${subjectPrefix}:ref:refs/heads/main`,
          },
        },
      ),
      maxSessionDuration: Duration.hours(1),
    });
    for (const repository of [this.apiRepo, this.webRepo])
      repository.grantPullPush(deployRole);
    deployRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ["ecr:ListImages"],
        resources: [this.apiRepo.repositoryArn, this.webRepo.repositoryArn],
      }),
    );
    deployRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ["sts:AssumeRole"],
        resources: [
          `arn:aws:iam::${this.account}:role/cdk-hnb659fds-deploy-role-${this.account}-${this.region}`,
          `arn:aws:iam::${this.account}:role/cdk-hnb659fds-file-publishing-role-${this.account}-${this.region}`,
          `arn:aws:iam::${this.account}:role/cdk-hnb659fds-lookup-role-${this.account}-${this.region}`,
        ],
      }),
    );
    deployRole.addToPolicy(
      new iam.PolicyStatement({
        actions: [
          "cloudformation:DescribeStacks",
          "cloudformation:DescribeStackEvents",
          "cloudformation:GetTemplate",
        ],
        resources: [
          `arn:aws:cloudformation:${this.region}:${this.account}:stack/Talyn*/*`,
        ],
      }),
    );
    deployRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ["ssm:GetParameter"],
        resources: [
          `arn:aws:ssm:${this.region}:${this.account}:parameter/cdk-bootstrap/hnb659fds/version`,
        ],
      }),
    );
    deployRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ["ecs:DescribeServices", "ecs:DescribeTasks", "ecs:ListTasks"],
        resources: ["*"],
        conditions: { ArnEquals: { "ecs:cluster": this.cluster.clusterArn } },
      }),
    );
    const scheduleRole = new iam.Role(this, "SchedulerRole", {
      assumedBy: new iam.ServicePrincipal("scheduler.amazonaws.com"),
    });
    this.queue.grantSendMessages(scheduleRole);
    new scheduler.CfnSchedule(this, "MaintenanceSchedule", {
      flexibleTimeWindow: { mode: "FLEXIBLE", maximumWindowInMinutes: 2 },
      scheduleExpression: "rate(15 minutes)",
      target: {
        arn: this.queue.queueArn,
        roleArn: scheduleRole.roleArn,
        input: JSON.stringify({ kind: "sweep" }),
        retryPolicy: {
          maximumRetryAttempts: 2,
          maximumEventAgeInSeconds: 3600,
        },
      },
    });
    const outputs: Record<string, string> = {
      ApiRepository: this.apiRepo.repositoryUri,
      WebRepository: this.webRepo.repositoryUri,
      Bucket: this.bucket.bucketName,
      DatabaseHost: this.db.dbInstanceEndpointAddress,
      QueueUrl: this.queue.queueUrl,
      Cluster: this.cluster.clusterName,
      GithubRoleArn: deployRole.roleArn,
      AlertsTopic: this.alerts.topicArn,
      CognitoPool: this.pool.userPoolId,
    };
    for (const [name, value] of Object.entries(outputs))
      new CfnOutput(this, "Output" + name, { value }).overrideLogicalId(name);
  }
}

interface RuntimeProps extends StackProps {
  foundation: Foundation;
  domain?: string;
  certificateArn?: string;
  senderEmail: string;
  imageTag: string;
}
export class Runtime extends Construct {
  get region() {
    return Stack.of(this).region;
  }
  get account() {
    return Stack.of(this).account;
  }
  constructor(scope: Construct, id: string, props: RuntimeProps) {
    super(scope, id);
    const f = props.foundation;
    Tags.of(this).add("Project", "talyn");
    Tags.of(this).add("Environment", "development");
    const customDomain = Boolean(props.domain && props.certificateArn);
    const alb = new elb.ApplicationLoadBalancer(this, "LoadBalancer", {
      vpc: f.vpc,
      internetFacing: customDomain,
      vpcSubnets: customDomain
        ? { subnetType: ec2.SubnetType.PUBLIC }
        : { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      idleTimeout: Duration.seconds(120),
      dropInvalidHeaderFields: true,
    });
    const webTarget = new elb.ApplicationTargetGroup(this, "WebTarget", {
      vpc: f.vpc,
      port: 3000,
      protocol: elb.ApplicationProtocol.HTTP,
      targetType: elb.TargetType.IP,
      healthCheck: { path: "/", healthyHttpCodes: "200" },
      deregistrationDelay: Duration.seconds(120),
    });
    const apiTarget = new elb.ApplicationTargetGroup(this, "ApiTarget", {
      vpc: f.vpc,
      port: 8000,
      protocol: elb.ApplicationProtocol.HTTP,
      targetType: elb.TargetType.IP,
      healthCheck: { path: "/api/health", healthyHttpCodes: "200" },
      deregistrationDelay: Duration.seconds(120),
    });
    let listener: elb.ApplicationListener;
    let url: string;
    if (customDomain) {
      url = `https://${props.domain}`;
      alb.addRedirect({
        sourceProtocol: elb.ApplicationProtocol.HTTP,
        sourcePort: 80,
        targetProtocol: elb.ApplicationProtocol.HTTPS,
        targetPort: 443,
      });
      listener = alb.addListener("Https", {
        port: 443,
        certificates: [
          acm.Certificate.fromCertificateArn(
            this,
            "TlsCertificate",
            props.certificateArn!,
          ),
        ],
        sslPolicy: elb.SslPolicy.TLS13_RES,
        defaultTargetGroups: [webTarget],
      });
    } else if (this.node.tryGetContext("ingress") === "ip") {
      const gateway = ipGateway(
        this,
        f.vpc,
        alb.loadBalancerDnsName,
        props.senderEmail,
        f.alerts,
      );
      alb.connections.allowFrom(
        gateway.security,
        ec2.Port.tcp(80),
        "Private HTTPS gateway origin",
      );
      listener = alb.addListener("PrivateHttp", {
        port: 80,
        open: false,
        defaultTargetGroups: [webTarget],
      });
      url = gateway.url;
    } else {
      const prefixId =
        this.node.tryGetContext("cloudFrontPrefixListId") ||
        ec2.PrefixList.fromLookup(this, "CloudFrontPrefix", {
          prefixListName: "com.amazonaws.global.cloudfront.origin-facing",
        }).prefixListId;
      alb.connections.allowFrom(
        ec2.Peer.prefixList(prefixId),
        ec2.Port.tcp(80),
        "CloudFront private VPC origin only",
      );
      listener = alb.addListener("PrivateHttp", {
        port: 80,
        open: false,
        defaultTargetGroups: [webTarget],
      });
      const origin = new cloudfront.VpcOrigin(this, "PrivateOrigin", {
        endpoint: cloudfront.VpcOriginEndpoint.applicationLoadBalancer(alb),
        protocolPolicy: cloudfront.OriginProtocolPolicy.HTTP_ONLY,
      });
      origin.node.addDependency(listener);
      const distribution = new cloudfront.Distribution(this, "Distribution", {
        comment: "Talyn development HTTPS without a custom domain",
        defaultBehavior: {
          origin: origins.VpcOrigin.withVpcOrigin(origin, {
            readTimeout: Duration.seconds(60),
            keepaliveTimeout: Duration.seconds(60),
          }),
          viewerProtocolPolicy:
            cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
          allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
          cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
          originRequestPolicy: cloudfront.OriginRequestPolicy.ALL_VIEWER,
        },
        enableLogging: false,
      });
      url = `https://${distribution.distributionDomainName}`;
    }
    listener.addTargetGroups("ApiRoute", {
      priority: 10,
      conditions: [elb.ListenerCondition.pathPatterns(["/api/*"])],
      targetGroups: [apiTarget],
    });
    f.bucket.addCorsRule({
      allowedOrigins: [url],
      allowedMethods: [
        s3.HttpMethods.PUT,
        s3.HttpMethods.GET,
        s3.HttpMethods.HEAD,
      ],
      allowedHeaders: ["content-type", "x-amz-checksum-sha256"],
      exposedHeaders: ["ETag"],
      maxAge: 300,
    });
    f.appSg.addIngressRule(
      alb.connections.securityGroups[0],
      ec2.Port.tcp(8000),
      "API routing",
      true,
    );
    f.appSg.addIngressRule(
      alb.connections.securityGroups[0],
      ec2.Port.tcp(3000),
      "Web routing",
      true,
    );
    const configSet = new ses.ConfigurationSet(this, "EmailConfiguration", {
      configurationSetName: "talyn-development",
      reputationMetrics: true,
      sendingEnabled: true,
    });
    new ses.CfnConfigurationSetEventDestination(this, "EmailDeliveryEvents", {
      configurationSetName: configSet.configurationSetName,
      eventDestination: {
        enabled: true,
        name: "delivery-events",
        matchingEventTypes: [
          "send",
          "delivery",
          "bounce",
          "complaint",
          "reject",
        ],
        snsDestination: { topicArn: f.emailEvents.topicArn },
      },
    });
    const apiRole = new iam.Role(this, "ApiTaskRole", {
      assumedBy: new iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
    });
    const workerRole = new iam.Role(this, "WorkerTaskRole", {
      assumedBy: new iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
    });
    const llmProvider = this.node.tryGetContext("llmProvider") || "bedrock";
    const groqSecretArn = this.node.tryGetContext("groqSecretArn");
    if (llmProvider === "groq" && !groqSecretArn)
      throw new Error(
        "Groq requires groqSecretArn context, never the key itself",
      );
    const groqSecret = groqSecretArn
      ? secrets.Secret.fromSecretCompleteArn(this, "GroqSecret", groqSecretArn)
      : undefined;
    for (const role of [apiRole, workerRole]) {
      f.db.secret!.grantRead(role);
      f.key.grantEncryptDecrypt(role);
      if (llmProvider === "bedrock")
        role.addToPolicy(
          new iam.PolicyStatement({
            actions: ["bedrock:InvokeModel"],
            resources: [
              `arn:aws:bedrock:${this.region}:${this.account}:inference-profile/apac.amazon.nova-lite-v1:0`,
              "arn:aws:bedrock:ap-*::foundation-model/amazon.nova-lite-v1:0",
            ],
          }),
        );
    }
    apiRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ["s3:GetObject", "s3:PutObject"],
        resources: [f.bucket.arnForObjects("*")],
      }),
    );
    apiRole.addToPolicy(
      new iam.PolicyStatement({
        actions: [
          "polly:SynthesizeSpeech",
          "transcribe:StartStreamTranscription",
        ],
        resources: ["*"],
      }),
    );
    apiRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ["cognito-idp:ListUsers"],
        resources: [f.pool.userPoolArn],
      }),
    );
    f.bucket.grantReadWrite(workerRole);
    workerRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ["s3:ListBucketVersions"],
        resources: [f.bucket.bucketArn],
      }),
    );
    workerRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ["s3:DeleteObjectVersion"],
        resources: [f.bucket.arnForObjects("*")],
      }),
    );
    f.queue.grantConsumeMessages(workerRole);
    f.queue.grantSendMessages(workerRole);
    f.eventQueue.grantConsumeMessages(workerRole);
    workerRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ["ses:SendEmail"],
        resources: [
          `arn:aws:ses:${this.region}:${this.account}:identity/${props.senderEmail}`,
          `arn:aws:ses:${this.region}:${this.account}:identity/${props.senderEmail.split("@")[1]}`,
          `arn:aws:ses:${this.region}:${this.account}:configuration-set/${configSet.configurationSetName}`,
        ],
        conditions: { StringEquals: { "ses:FromAddress": props.senderEmail } },
      }),
    );
    workerRole.addToPolicy(
      new iam.PolicyStatement({
        actions: [
          "rekognition:DetectFaces",
          "textract:StartDocumentTextDetection",
          "textract:GetDocumentTextDetection",
        ],
        resources: ["*"],
      }),
    );
    const additionalRecipients = String(
      this.node.tryGetContext("additionalEmailRecipients") || "",
    )
      .split(",")
      .map((email) => email.trim().toLowerCase())
      .filter(Boolean);
    if (
      additionalRecipients.length > 20 ||
      additionalRecipients.some(
        (email) => !/^[^\s@,]+@[^\s@,]+\.[^\s@,]+$/.test(email),
      )
    ) {
      throw new Error(
        "additionalEmailRecipients must contain at most 20 valid email addresses",
      );
    }
    const emailAllowlist = Array.from(
      new Set([
        props.senderEmail.toLowerCase(),
        "success@simulator.amazonses.com",
        ...additionalRecipients,
      ]),
    ).join(",");
    const environment = {
      TALYN_MODE: "aws",
      TALYN_LLM_PROVIDER: llmProvider,
      TALYN_MAX_CONCURRENT: llmProvider === "groq" ? "2" : "10",
      TALYN_ENVIRONMENT: "production",
      TALYN_REGION: this.region,
      TALYN_PUBLIC_URL: url,
      TALYN_DATABASE_HOST: f.db.dbInstanceEndpointAddress,
      TALYN_DATABASE_SECRET_ARN: f.db.secret!.secretArn,
      TALYN_COGNITO_POOL_ID: f.pool.userPoolId,
      TALYN_COGNITO_CLIENT_ID: f.client.userPoolClientId,
      TALYN_BUCKET: f.bucket.bucketName,
      TALYN_QUEUE_URL: f.queue.queueUrl,
      TALYN_EVENT_QUEUE_URL: f.eventQueue.queueUrl,
      TALYN_DATA_DIR: "/tmp/talyn",
      TALYN_SENDER_EMAIL: props.senderEmail,
      TALYN_SES_CONFIGURATION_SET: configSet.configurationSetName,
      TALYN_LIVE_EMAIL: "false",
      TALYN_EMAIL_ALLOWLIST: emailAllowlist,
      LANGSMITH_TRACING: "false",
      LANGCHAIN_TRACING_V2: "false",
    };
    const define = (
      name: string,
      role: iam.IRole,
      cpu: number,
      memory: number,
      isWeb = false,
    ) => {
      const task = new ecs.FargateTaskDefinition(this, `${name}Task`, {
        cpu,
        memoryLimitMiB: memory,
        taskRole: role,
        runtimePlatform: {
          operatingSystemFamily: ecs.OperatingSystemFamily.LINUX,
          cpuArchitecture: ecs.CpuArchitecture.X86_64,
        },
        volumes: [{ name: "tmp" }],
      });
      const group = new logs.LogGroup(this, `${name}Logs`, {
        retention: logs.RetentionDays.TWO_WEEKS,
        removalPolicy: RemovalPolicy.RETAIN,
        encryptionKey: f.key,
      });
      const container = task.addContainer(name, {
        image: ecs.ContainerImage.fromEcrRepository(
          isWeb ? f.webRepo : f.apiRepo,
          props.imageTag,
        ),
        logging: ecs.LogDrivers.awsLogs({
          logGroup: group,
          streamPrefix: name,
        }),
        environment: isWeb
          ? { NODE_ENV: "production", HOSTNAME: "0.0.0.0", PORT: "3000" }
          : environment,
        secrets: isWeb
          ? undefined
          : {
              TALYN_SESSION_SECRET: ecs.Secret.fromSecretsManager(
                f.sessionSecret,
              ),
              ...(groqSecret
                ? {
                    TALYN_GROQ_API_KEY:
                      ecs.Secret.fromSecretsManager(groqSecret),
                  }
                : {}),
            },
        command: isWeb
          ? undefined
          : [
              "python",
              "-m",
              "app.launch",
              name === "Worker" ? "worker" : "api",
            ],
        readonlyRootFilesystem: !isWeb,
        stopTimeout: Duration.seconds(120),
        linuxParameters: new ecs.LinuxParameters(this, `${name}Linux`, {
          initProcessEnabled: true,
        }),
      });
      container.addMountPoints({
        sourceVolume: "tmp",
        containerPath: "/tmp",
        readOnly: false,
      });
      if (name !== "Worker")
        container.addPortMappings({ containerPort: isWeb ? 3000 : 8000 });
      const service = new ecs.FargateService(this, `${name}Service`, {
        cluster: f.cluster,
        taskDefinition: task,
        desiredCount: 1,
        assignPublicIp: true,
        vpcSubnets: { subnetType: ec2.SubnetType.PUBLIC },
        securityGroups: [f.appSg],
        circuitBreaker: { rollback: true },
        minHealthyPercent: 100,
        maxHealthyPercent: 200,
        healthCheckGracePeriod:
          name === "Worker" ? undefined : Duration.seconds(180),
        enableExecuteCommand: false,
      });
      const alarm = new cloudwatch.Alarm(this, `${name}CpuAlarm`, {
        metric: service.metricCpuUtilization(),
        threshold: 80,
        evaluationPeriods: 3,
      });
      alarm.addAlarmAction(new actions.SnsAction(f.alerts));
      return { service, task };
    };
    const api = define("Api", apiRole, 512, 1024);
    define("Worker", workerRole, 512, 1024);
    const webRole = new iam.Role(this, "WebTaskRole", {
      assumedBy: new iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
    });
    const web = define("Web", webRole, 256, 512, true);
    // KMS grants to the regional CloudWatch Logs service, scoped to this account's log groups.
    f.key.addToResourcePolicy(
      new iam.PolicyStatement({
        principals: [
          new iam.ServicePrincipal(`logs.${this.region}.amazonaws.com`),
        ],
        actions: [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:DescribeKey",
        ],
        resources: ["*"],
        conditions: {
          ArnLike: {
            "kms:EncryptionContext:aws:logs:arn": `arn:aws:logs:${this.region}:${this.account}:log-group:*`,
          },
        },
      }),
    );
    webTarget.addTarget(web.service);
    apiTarget.addTarget(api.service);
    const errors = new cloudwatch.Alarm(this, "ServerErrorAlarm", {
      metric: alb.metrics.httpCodeTarget(elb.HttpCodeTarget.TARGET_5XX_COUNT),
      threshold: 5,
      evaluationPeriods: 2,
    });
    errors.addAlarmAction(new actions.SnsAction(f.alerts));
    new CfnOutput(this, "ApplicationUrl", { value: url }).overrideLogicalId(
      "ApplicationUrl",
    );
    new CfnOutput(this, "LoadBalancerDns", { value: alb.loadBalancerDnsName });
    new CfnOutput(this, "OutputApiService", {
      value: api.service.serviceName,
    }).overrideLogicalId("ApiService");
  }
}
