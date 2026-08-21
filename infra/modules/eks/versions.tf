terraform {
  required_version = ">= 1.15.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.61"
    }
    time = {
      source  = "hashicorp/time"
      version = ">= 0.14.1"
    }
    tls = {
      source  = "hashicorp/tls"
      version = ">= 4.3"
    }
  }
}
