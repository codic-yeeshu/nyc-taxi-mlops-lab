resource "aws_security_group" "service" {
  for_each = toset(["platform", "app", "llm", "rds"])

  name        = "lab-${each.key}"
  description = "Network access for the lab ${each.key} service"
  vpc_id      = data.aws_vpc.default.id
}

resource "aws_vpc_security_group_egress_rule" "host_outbound" {
  for_each = toset(["platform", "app", "llm"])

  security_group_id = aws_security_group.service[each.key].id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

resource "aws_vpc_security_group_ingress_rule" "app_http" {
  for_each = toset([for cidr in var.ingress_cidrs : cidr if can(cidrnetmask(cidr))])

  security_group_id = aws_security_group.service["app"].id
  cidr_ipv4         = each.value
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
}

resource "aws_vpc_security_group_ingress_rule" "app_http_ipv6" {
  for_each = toset([for cidr in var.ingress_cidrs : cidr if !can(cidrnetmask(cidr))])

  security_group_id = aws_security_group.service["app"].id
  cidr_ipv6         = each.value
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
}

locals {
  internal_ingress = {
    for rule in [
      { source = "app", target = "platform", port = 5000 },
      { source = "app", target = "llm", port = 8080 },
      { source = "app", target = "llm", port = 8081 },
      { source = "platform", target = "llm", port = 8080 },
      { source = "platform", target = "llm", port = 8081 },
      { source = "app", target = "rds", port = 5432 },
      { source = "platform", target = "rds", port = 5432 },
    ] : "${rule.source}-${rule.target}-${rule.port}" => rule
  }
}

resource "aws_vpc_security_group_ingress_rule" "internal" {
  for_each = local.internal_ingress

  security_group_id            = aws_security_group.service[each.value.target].id
  referenced_security_group_id = aws_security_group.service[each.value.source].id
  ip_protocol                  = "tcp"
  from_port                    = each.value.port
  to_port                      = each.value.port
}
