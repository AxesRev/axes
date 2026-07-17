variable "repository_names" {
  description = "ECR repository names to create."
  type        = list(string)
}

variable "tags" {
  description = "Tags applied to all repositories."
  type        = map(string)
  default     = {}
}
