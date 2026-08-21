variable "state_bucket_name" {
  description = "S3 bucket that holds Terragrunt remote state for every other stack."
  type        = string
}

variable "github_repository" {
  description = "GitHub org/repo allowed to assume the deploy role (OIDC sub repo:ORG/REPO:*)."
  type        = string
}

variable "role_name" {
  description = "IAM role name assumed by GitHub Actions. Must match the ARN hardcoded in workflows."
  type        = string
  default     = "github-actions-deploy"
}

variable "role_max_session_duration" {
  description = "Seconds the deploy role can be assumed. Must cover the longest GHA job timeout."
  type        = number
  default     = 14400
}

variable "tags" {
  description = "Tags applied to bootstrap resources."
  type        = map(string)
  default     = {}
}
