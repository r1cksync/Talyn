import { test } from "node:test";
import { App } from "aws-cdk-lib";
import { Template, Match } from "aws-cdk-lib/assertions";
import { Foundation, Runtime } from "../lib/stacks";
import * as cloudfront from "aws-cdk-lib/aws-cloudfront";
test("AWS-generated HTTPS address routes through a private uncached VPC origin", () => {
  const app = new App({
    context: { cloudFrontPrefixListId: "pl-00000000000000000" },
  });
  const foundation = new Foundation(app, "CloudFrontFoundation", {
    env: { account: "111111111111", region: "ap-south-1" },
  });
  new Runtime(foundation, "Runtime", {
    foundation,
    senderEmail: "sender@example.com",
    imageTag: "fixture",
  });
  const template = Template.fromStack(foundation);
  template.hasResourceProperties("AWS::ElasticLoadBalancingV2::LoadBalancer", {
    Scheme: "internal",
  });
  template.resourceCountIs("AWS::CloudFront::VpcOrigin", 1);
  template.hasResourceProperties("AWS::CloudFront::Distribution", {
    DistributionConfig: {
      DefaultCacheBehavior: {
        ViewerProtocolPolicy: "redirect-to-https",
        CachePolicyId: cloudfront.CachePolicy.CACHING_DISABLED.cachePolicyId,
        OriginRequestPolicyId:
          cloudfront.OriginRequestPolicy.ALL_VIEWER.originRequestPolicyId,
      },
    },
  });
  template.resourceCountIs("AWS::CertificateManager::Certificate", 0);
});
test("private storage, isolated TLS database, HTTPS routing, scoped OIDC, zero NAT", () => {
  const app = new App({
    context: {
      domain: "talyn.example.com",
      monthlyBudget: 150,
      githubRepository: "r1cksync/Talyn",
    },
  });
  const foundation = new Foundation(app, "TestFoundation", {
    env: { account: "111111111111", region: "ap-south-1" },
  });
  new Runtime(foundation, "Runtime", {
    env: { account: "111111111111", region: "ap-south-1" },
    foundation,
    domain: "talyn.example.com",
    certificateArn:
      "arn:aws:acm:ap-south-1:111111111111:certificate/00000000-0000-0000-0000-000000000000",
    senderEmail: "sender@example.com",
    imageTag: "fixture",
  });
  const base = Template.fromStack(foundation),
    service = base;
  base.resourceCountIs("AWS::EC2::NatGateway", 0);
  base.hasResourceProperties("AWS::S3::Bucket", {
    PublicAccessBlockConfiguration: {
      BlockPublicAcls: true,
      BlockPublicPolicy: true,
      IgnorePublicAcls: true,
      RestrictPublicBuckets: true,
    },
    VersioningConfiguration: { Status: "Enabled" },
  });
  base.hasResourceProperties("AWS::RDS::DBInstance", {
    PubliclyAccessible: false,
    StorageEncrypted: true,
    DeletionProtection: true,
    BackupRetentionPeriod: 7,
  });
  base.hasResourceProperties("AWS::IAM::Role", {
    AssumeRolePolicyDocument: {
      Statement: Match.arrayWith([
        Match.objectLike({
          Condition: {
            StringEquals: {
              "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
              "token.actions.githubusercontent.com:sub":
                "repo:r1cksync/Talyn:ref:refs/heads/main",
            },
          },
        }),
      ]),
    },
  });
  service.hasResourceProperties("AWS::ElasticLoadBalancingV2::Listener", {
    Port: 443,
    Protocol: "HTTPS",
  });
  service.resourceCountIs("AWS::ECS::Service", 3);
  service.hasResourceProperties("AWS::ECS::TaskDefinition", {
    ContainerDefinitions: Match.arrayWith([
      Match.objectLike({
        Environment: Match.arrayWith([
          { Name: "TALYN_MODE", Value: "aws" },
          { Name: "TALYN_ENVIRONMENT", Value: "production" },
        ]),
      }),
    ]),
  });
});
