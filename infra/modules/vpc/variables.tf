variable "name" {
  description = "Name prefix for VPC resources."
  type        = string
}

variable "cidr" {
  description = "VPC CIDR block."
  type        = string
}

variable "azs" {
  description = "Availability zones to use."
  type        = list(string)
}

variable "private_subnets" {
  description = "Private subnet CIDRs (one per AZ)."
  type        = list(string)
}

variable "public_subnets" {
  description = "Public subnet CIDRs (one per AZ)."
  type        = list(string)
}

variable "enable_nat_gateway" {
  description = "Provision NAT gateway(s) for private subnet egress."
  type        = bool
  default     = true
}

variable "single_nat_gateway" {
  description = "Use a single NAT gateway (cheaper for non-prod)."
  type        = bool
  default     = true
}

variable "public_subnet_tags" {
  description = "Extra tags applied only to public subnets."
  type        = map(string)
  default     = {}
}

variable "private_subnet_tags" {
  description = "Extra tags applied only to private subnets."
  type        = map(string)
  default     = {}
}

variable "tags" {
  description = "Tags applied to all VPC resources."
  type        = map(string)
  default     = {}
}
