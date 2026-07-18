variable "cluster_name" {
  description = "EKS cluster name."
  type        = string
}

variable "cluster_version" {
  description = "Kubernetes version for the EKS control plane."
  type        = string
  default     = "1.31"
}

variable "vpc_id" {
  description = "VPC ID for the cluster."
  type        = string
}

variable "subnet_ids" {
  description = "Subnet IDs for the control plane and managed nodes (typically private)."
  type        = list(string)
}

variable "public_subnet_ids" {
  description = "Public subnet IDs to tag for internet-facing load balancers. Empty skips those tags."
  type        = list(string)
  default     = []
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
  default     = ["t3.small"]
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

variable "tags" {
  description = "Tags applied to all resources."
  type        = map(string)
  default     = {}
}
