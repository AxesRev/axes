terraform {
  required_version = ">= 1.15.8"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.55"
    }
    tls = {
      source  = "hashicorp/tls"
      version = ">= 4.3"
    }
  }
}
