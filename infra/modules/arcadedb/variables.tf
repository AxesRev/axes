variable "namespace" {
  description = "Kubernetes namespace for ArcadeDB."
  type        = string
  default     = "arcadedb"
}

variable "image" {
  description = "ArcadeDB container image."
  type        = string
  default     = "arcadedata/arcadedb:26.11.1"
}

variable "storage_size" {
  description = "Persistent volume size for ArcadeDB databases and security config."
  type        = string
  default     = "20Gi"
}

variable "password" {
  description = "ArcadeDB root password. If null, a random password is generated."
  type        = string
  default     = null
  sensitive   = true
}

variable "create_storage_class" {
  description = "Create a gp3 StorageClass (EBS CSI). Set false if one already exists."
  type        = bool
  default     = true
}

variable "storage_class_name" {
  description = "StorageClass name for the ArcadeDB PVC."
  type        = string
  default     = "gp3"
}
