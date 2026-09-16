import { CfnOutput, Duration, Stack } from "aws-cdk-lib";
import { Construct } from "constructs";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as iam from "aws-cdk-lib/aws-iam";
import * as sns from "aws-cdk-lib/aws-sns";
import * as cloudwatch from "aws-cdk-lib/aws-cloudwatch";
import * as actions from "aws-cdk-lib/aws-cloudwatch-actions";

/** Domain-free development HTTPS when CloudFront account verification is blocked. */
export function ipGateway(
  scope: Construct,
  vpc: ec2.IVpc,
  backend: string,
  email: string,
  alerts: sns.ITopic,
) {
  const security = new ec2.SecurityGroup(scope, "IpGatewaySecurity", { vpc });
  security.addIngressRule(
    ec2.Peer.anyIpv4(),
    ec2.Port.tcp(80),
    "ACME validation and HTTPS redirect",
  );
  security.addIngressRule(
    ec2.Peer.anyIpv4(),
    ec2.Port.tcp(443),
    "HTTPS and authenticated WebSockets",
  );
  const address = new ec2.CfnEIP(scope, "IpGatewayAddress", { domain: "vpc" });
  const role = new iam.Role(scope, "IpGatewayRole", {
    assumedBy: new iam.ServicePrincipal("ec2.amazonaws.com"),
  });
  role.addManagedPolicy(
    iam.ManagedPolicy.fromAwsManagedPolicyName("AmazonSSMManagedInstanceCore"),
  );
  role.addToPolicy(
    new iam.PolicyStatement({
      actions: ["cloudwatch:PutMetricData"],
      resources: ["*"],
      conditions: { StringEquals: { "cloudwatch:namespace": "Talyn/TLS" } },
    }),
  );
  const gateway = new ec2.Instance(scope, "IpGateway", {
    vpc,
    vpcSubnets: { subnetType: ec2.SubnetType.PUBLIC },
    securityGroup: security,
    // This account's regional EC2 quota is one vCPU; T2 micro fits that limit.
    instanceType: new ec2.InstanceType("t2.micro"),
    machineImage: ec2.MachineImage.latestAmazonLinux2023({
      cpuType: ec2.AmazonLinuxCpuType.X86_64,
    }),
    role,
    userDataCausesReplacement: true,
    requireImdsv2: true,
    blockDevices: [
      {
        deviceName: "/dev/xvda",
        volume: ec2.BlockDeviceVolume.ebs(8, {
          encrypted: true,
          volumeType: ec2.EbsDeviceVolumeType.GP3,
        }),
      },
    ],
  });
  new ec2.CfnEIPAssociation(scope, "IpGatewayAssociation", {
    allocationId: address.attrAllocationId,
    instanceId: gateway.instanceId,
  });
  const ip = address.attrPublicIp;
  const write = (path: string, value: string) =>
    gateway.userData.addCommands(
      `cat > ${path} <<'TALYN_FILE'`,
      value,
      "TALYN_FILE",
    );
  gateway.userData.addCommands(
    "set -eu",
    "dnf install -y nginx python3.11 python3.11-pip",
    "python3.11 -m venv /opt/talyn-certbot",
    "/opt/talyn-certbot/bin/pip install --no-cache-dir certbot==5.8.0",
    "mkdir -p /var/lib/talyn-acme",
  );
  write(
    "/etc/nginx/nginx.conf",
    `user nginx;
worker_processes auto;
pid /run/nginx.pid;
error_log /var/log/nginx/error.log warn;
events { worker_connections 1024; }
http {
  include /etc/nginx/mime.types;
  access_log off;
  server_tokens off;
  map $http_upgrade $connection_upgrade { default upgrade; '' close; }
  include /etc/nginx/conf.d/*.conf;
}`,
  );
  write(
    "/etc/nginx/conf.d/talyn-http.conf",
    `server {
  listen 80 default_server;
  server_name ${ip};
  location ^~ /.well-known/acme-challenge/ { root /var/lib/talyn-acme; }
  location / { return 308 https://${ip}$request_uri; }
}`,
  );
  write(
    "/usr/local/bin/talyn-tls-metric",
    `#!/bin/bash
set -eu
remaining=0
if [ -f /etc/letsencrypt/live/talyn-ip/cert.pem ]; then
  expires=$(openssl x509 -enddate -noout -in /etc/letsencrypt/live/talyn-ip/cert.pem | cut -d= -f2)
  remaining=$(( $(date -d "$expires" +%s) - $(date +%s) ))
fi
aws cloudwatch put-metric-data --region ${Stack.of(scope).region} --namespace Talyn/TLS --metric-data "MetricName=CertificateSecondsRemaining,Value=$remaining,Unit=Seconds,Dimensions=[{Name=Gateway,Value=talyn}]"
`,
  );
  const quote = (value: string) => "'" + value.replace(/'/g, "'\\''") + "'";
  write(
    "/usr/local/bin/talyn-tls-configure",
    `#!/bin/bash
set -eu
trap '/usr/local/bin/talyn-tls-metric || true' EXIT
/opt/talyn-certbot/bin/certbot certonly --non-interactive --agree-tos --email ${quote(email)} --preferred-profile shortlived --webroot --webroot-path /var/lib/talyn-acme --ip-address ${ip} --cert-name talyn-ip --keep-until-expiring
cat > /etc/nginx/conf.d/talyn-https.conf <<'TALYN_NGINX'
server {
  listen 443 ssl;
  server_name ${ip};
  ssl_certificate /etc/letsencrypt/live/talyn-ip/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/talyn-ip/privkey.pem;
  ssl_protocols TLSv1.2 TLSv1.3;
  add_header Strict-Transport-Security "max-age=86400" always;
  client_max_body_size 21m;
  resolver 169.254.169.253 valid=30s;
  resolver_timeout 10s;
  set $talyn_backend ${backend};
  location / {
    proxy_pass http://$talyn_backend$request_uri;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_read_timeout 125s;
    proxy_send_timeout 125s;
    proxy_buffering off;
    proxy_request_buffering off;
  }
}
TALYN_NGINX
nginx -t
systemctl reload nginx
`,
  );
  write(
    "/etc/systemd/system/talyn-tls.service",
    `[Unit]
Description=Issue or renew Talyn IP TLS certificate and reload nginx
After=network-online.target nginx.service
Wants=network-online.target
StartLimitIntervalSec=0
[Service]
Type=oneshot
ExecStart=/usr/local/bin/talyn-tls-configure
Restart=on-failure
RestartSec=60
`,
  );
  write(
    "/etc/systemd/system/talyn-tls.timer",
    `[Unit]
Description=Check short-lived Talyn certificate every four hours
[Timer]
OnBootSec=30
OnUnitActiveSec=4h
RandomizedDelaySec=60
Persistent=true
[Install]
WantedBy=timers.target
`,
  );
  gateway.userData.addCommands(
    "chmod 750 /usr/local/bin/talyn-tls-*",
    "systemctl enable --now nginx",
    "systemctl daemon-reload",
    "systemctl enable --now talyn-tls.timer",
    "systemctl start --no-block talyn-tls.service",
  );
  const certificate = new cloudwatch.Alarm(scope, "CertificateExpiryAlarm", {
    metric: new cloudwatch.Metric({
      namespace: "Talyn/TLS",
      metricName: "CertificateSecondsRemaining",
      dimensionsMap: { Gateway: "talyn" },
      period: Duration.hours(6),
      statistic: "Minimum",
    }),
    threshold: 86400,
    evaluationPeriods: 1,
    comparisonOperator: cloudwatch.ComparisonOperator.LESS_THAN_THRESHOLD,
    treatMissingData: cloudwatch.TreatMissingData.BREACHING,
  });
  certificate.addAlarmAction(new actions.SnsAction(alerts));
  new CfnOutput(scope, "IpGatewayInstance", {
    value: gateway.instanceId,
  }).overrideLogicalId("IpGatewayInstance");
  return { url: `https://${ip}`, security };
}
