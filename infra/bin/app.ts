import { App } from "aws-cdk-lib";
import { Foundation, Runtime } from "../lib/stacks";
const app = new App();
const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: app.node.tryGetContext("region") || "ap-south-1",
};
const foundation = new Foundation(app, "TalynFoundation", { env });
const domain = app.node.tryGetContext("domain");
const certificateArn = app.node.tryGetContext("certificateArn");
const senderEmail = app.node.tryGetContext("senderEmail");
if (
  senderEmail &&
  (app.node.tryGetContext("runtime") === "true" || (domain && certificateArn))
)
  new Runtime(foundation, "Runtime", {
    env,
    foundation,
    domain,
    certificateArn,
    senderEmail,
    imageTag: app.node.tryGetContext("imageTag") || "initial",
  });
