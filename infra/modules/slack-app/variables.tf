variable "name" {
  description = "Name prefix for AWS resources."
  type        = string
}

variable "vpc_id" {
  type = string
}

variable "vpc_cidr" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "node_security_group_id" {
  description = "EKS node SG; ingress opened for the NLB NodePort."
  type        = string
}

variable "node_autoscaling_group_names" {
  description = "EKS managed node group ASG names for NLB instance targets."
  type        = list(string)
}

variable "namespace" {
  type    = string
  default = "slack-app"
}

variable "image" {
  description = "Container image from ECR."
  type        = string
}

variable "node_port" {
  description = "Static NodePort the internal NLB forwards to."
  type        = number
  default     = 30800
}

variable "replicas" {
  type    = number
  default = 1
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

variable "tags" {
  type    = map(string)
  default = {}
}
