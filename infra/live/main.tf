data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }

  filter {
    name   = "default-for-az"
    values = ["true"]
  }
}

data "aws_subnet" "host" {
  vpc_id            = data.aws_vpc.default.id
  availability_zone = var.availability_zone
  default_for_az    = true
}

module "host" {
  for_each = {
    platform = var.platform_instance_type
    app      = var.app_instance_type
    llm      = var.llm_instance_type
  }

  source             = "../modules/host"
  role               = each.key
  instance_type      = each.value
  subnet_id          = data.aws_subnet.host.id
  security_group_ids = [aws_security_group.service[each.key].id]
}

module "rds" {
  source             = "../modules/rds"
  instance_class     = var.rds_instance_class
  subnet_ids         = sort(data.aws_subnets.default.ids)
  security_group_ids = [aws_security_group.service["rds"].id]
}

module "artifact" {
  source = "../modules/bucket"
  name   = "lab-artifacts"
}

module "wiki" {
  source      = "../modules/secret"
  name        = "lab/wiki"
  description = "URL and token for the lab wiki"
}
