terraform {
  required_version = ">= 1.15.8"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.55"
    }
    vercel = {
      source  = "vercel/vercel"
      version = ">= 5.11.0"
    }
  }
}
