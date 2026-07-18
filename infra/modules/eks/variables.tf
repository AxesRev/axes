variable "cluster_name" {
  description = "EKS cluster name."
  type        = string
}

variable "cluster_version" {
  description = "Kubernetes version for the EKS control plane."
  type        = string
  default     = "1.36"
}

variable "vpc_id" {
  description = "VPC ID for the cluster."
  type        = string
}

variable "subnet_ids" {
  description = "Subnet IDs for the control plane and managed nodes (typically private)."
  type        = list(string)
}

variable "cluster_endpoint_public_access" {
  description = "Expose the Kubernetes API publicly."
  type        = bool
  default     = true
}

variable "cluster_endpoint_private_access" {
  description = "Expose the Kubernetes API on the VPC."
  type        = bool
  default     = true
}

variable "node_instance_types" {
  description = "EC2 instance types for the managed node group."
  type        = list(string)
  default     = ["t4g.medium"]
}

variable "node_ami_type" {
  description = "EKS optimized AMI type for the managed node group (must match CPU arch of instance types)."
  type        = string
  default     = "AL2023_ARM_64_STANDARD"
}

variable "node_desired_size" {
  description = "Desired number of worker nodes."
  type        = number
  default     = 2
}

variable "node_min_size" {
  description = "Minimum number of worker nodes."
  type        = number
  default     = 1
}

variable "node_max_size" {
  description = "Maximum number of worker nodes."
  type        = number
  default     = 4
}

variable "node_disk_size" {
  description = "Root volume size (GiB) for worker nodes."
  type        = number
  default     = 20
}

variable "additional_node_security_group_ids" {
  description = "Extra security groups attached to managed node ENIs (e.g. VPC db-clients)."
  type        = list(string)
  default     = []
}

variable "cluster_admin_principal_arn" {
  description = "IAM principal ARN granted cluster admin via EKS access entry (for local kubectl/MCP)."
  type        = string
}

variable "github_actions_deploy_role_arn" {
  description = "GitHub Actions deploy role ARN granted cluster admin via EKS access entry."
  type        = string
}

variable "additional_access_entries" {
  description = "Extra EKS access entries merged into the cluster access map."
  type = map(object({
    kubernetes_groups = optional(list(string))
    principal_arn     = string
    type              = optional(string, "STANDARD")
    user_name         = optional(string)
    tags              = optional(map(string), {})
    policy_associations = optional(map(object({
      policy_arn = string
      access_scope = object({
        namespaces = optional(list(string))
        type       = string
      })
    })), {})
  }))
  default = {}
}

variable "tags" {
  description = "Tags applied to all resources."
  type        = map(string)
  default     = {}
}
