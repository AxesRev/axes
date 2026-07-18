variable "namespace" {
  description = "Kubernetes namespace for Neo4j."
  type        = string
  default     = "neo4j"
}

variable "image" {
  description = "Neo4j container image."
  type        = string
  default     = "neo4j:5.26.28-community"
}

variable "volume_id" {
  description = "Existing EBS volume ID to mount (survives cluster destroy)."
  type        = string
}

variable "availability_zone" {
  description = "AZ of the EBS volume. Used for PV node affinity."
  type        = string
}

variable "size_gb" {
  description = "EBS volume size in GiB (must match the volume)."
  type        = number
}

variable "password" {
  description = "Neo4j password (from neo4j-data stack)."
  type        = string
  sensitive   = true
}
