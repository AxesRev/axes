variable "namespace" {
  type    = string
  default = "slack-app"
}

variable "image" {
  description = "Container image from ECR."
  type        = string
}

variable "node_port" {
  description = "Static NodePort the infra NLB forwards to. Must match slack-gateway."
  type        = number
}

variable "replicas" {
  type    = number
  default = 1
}

variable "server_url" {
  description = "Public HTTPS API Gateway URL from slack-gateway."
  type        = string
}

variable "ssm_secrets_parameter" {
  description = "Existing SSM SecureString JSON. Not managed by Terraform."
  type        = string
}

variable "ssm_generated_parameter" {
  description = "Terraform-owned SSM SecureString JSON."
  type        = string
}

variable "integrations_public_url" {
  description = "Public HTTPS URL of the integrations Lambda (Slack OAuth callback and GitHub connect links)."
  type        = string
}

variable "manifest_path" {
  description = "Repo path to slack_manifest.json. Used to re-run deploy when the file changes."
  type        = string
}

variable "deploy_manifest_script" {
  description = "Repo path to deploy_manifest.py. Runs after the Bolt pod is reachable."
  type        = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
