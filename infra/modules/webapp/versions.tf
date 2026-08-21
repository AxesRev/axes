terraform {
  required_version = ">= 1.15.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.61"
    }
    vercel = {
      source  = "vercel/vercel"
      version = ">= 5.12.0"
    }
  }
}
