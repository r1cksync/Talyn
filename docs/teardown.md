# AWS teardown record

Date: 17 September 2026. The owner explicitly requested deletion of Talyn and other chargeable resources in the AWS account, preserving S3 buckets. This superseded the earlier project-only cleanup scope.

The former development site is offline. Its public IP has been released and must not be used as a Talyn endpoint. The GitHub deployment workflow is disabled. Source code, local demo files and historical verification evidence remain in this repository.

## Resources removed

- `TalynFoundation` and `CDKToolkit` CloudFormation stacks, retaining their S3 buckets and required encryption dependency.
- Three Fargate services, their ECS cluster, the EC2 gateway, public IP, EBS volume, load balancer and project VPC resources.
- PostgreSQL, with deletion protection deliberately disabled and automated-backup deletion enabled; no final snapshot requested.
- Container repositories/images, project Lambda cleanup functions, application logs, alarms, scheduled maintenance and project deployment/runtime roles.
- Nineteen DynamoDB tables across two regions, three legacy Step Functions workflows, old project queues/topics, retained logs/dashboard, and an additional legacy Cognito user pool.
- Thirteen obsolete Talyn task definitions deregistered. Three standalone Secrets Manager secrets are scheduled for deletion; two unused customer-managed KMS keys are also scheduled for deletion.

Scheduled secrets and KMS keys do not incur their normal storage charge during the deletion window. This is distinct from past charges already accrued. See [Secrets Manager deletion](https://docs.aws.amazon.com/secretsmanager/latest/userguide/manage_delete-secret.html) and [KMS pricing](https://aws.amazon.com/kms/pricing/).

## Preserved storage and pending encryption choice

All 12 S3 buckets are preserved. The final comparison confirmed all 175 inventoried object versions, sizes, ETags, latest-version flags and delete markers were unchanged (344,211,059 bytes). A range read of an encrypted Talyn object succeeded after teardown. Bucket names and account-wide operator details are kept outside Git. One teardown template was added to the existing CDK asset bucket to let CloudFormation retain protected storage during deletion.

Talyn's 90 S3 objects use its customer-managed KMS key. That key remains enabled so the preserved files remain readable. It costs approximately US$1/month, plus applicable requests, in addition to retained S3 charges. The owner was asked whether to retain it or migrate S3 encryption first; no encryption migration or deletion of this key is authorized by a missing response. Other retained S3 objects use S3-managed encryption or the AWS-managed S3 KMS key, which has no monthly key-storage charge. [KMS pricing](https://aws.amazon.com/kms/pricing/).

Deleting the remaining key without migrating the objects would make their contents unrecoverable, despite the bucket and objects remaining present. [AWS key-deletion guidance](https://docs.aws.amazon.com/kms/latest/developerguide/deleting-keys.html).

## Verification scope

The account was inventoried across all 17 enabled commercial AWS regions, plus global CloudFront, Route 53, Marketplace agreements, Savings Plans and subscription checks. No active Marketplace agreements, Savings Plans, reserved instances, registered Route 53 domains, hosted zones or CloudFront distributions were found. The account has no Premium Support subscription.

The final regional inventory completed at **11:48 UTC / 17:18 IST**. It found no remaining EC2 instances, ECS clusters/tasks/services, EKS clusters, Lambda functions, RDS instances/clusters/backups, DynamoDB tables, load balancers, EBS volumes/snapshots, allocated public IPs, NAT gateways, paid VPC endpoints, ECR repositories, application queues, logs, alarms or scheduled jobs. The other inventoried compute, database and managed-hosting categories were empty. Targeted checks also confirmed both project stacks and both inventoried Cognito pools were gone. The GitHub deployment workflow is `disabled_manually`.

Remaining identified resources are S3, the single enabled S3-dependent customer key, two keys and three secrets pending deletion, and free control-plane resources such as AWS-managed keys, default event buses, service-managed rules and IAM metadata. Resource tagging can retain records of deleted resources; workload-specific APIs were used for final verification.

Inventory included compute/orchestration, databases, queues, API services, storage/backups, private networking, monitoring, security-service configurations and scheduled execution. Unsupported regional APIs were distinguished from populated services. AWS disables the legacy Glue development-endpoint API; its alternate list API returned an internal error. That legacy API could not be independently verified. No Glue resources appeared in the other inventory or recent billing results.

Private before/after inventory and action records are kept under `.local/aws-teardown/`, outside Git. Historical charges can continue to appear while AWS billing catches up; cleanup does not erase prior usage or tax. See [AWS guidance on unexpected charges](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/checklistforunwantedcharges.html). S3 and its explicitly retained encryption dependency are not represented as zero-cost storage.
