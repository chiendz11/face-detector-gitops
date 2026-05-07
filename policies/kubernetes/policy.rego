package main

import rego.v1

deny contains msg if {
  pod := pod_spec(input)
  workload_name := object.get(object.get(input, "metadata", {}), "name", "")
  not pod_runs_as_non_root(pod)
  not run_as_non_root_exception(input.kind, workload_name)
  msg := sprintf("%s %s must set spec.securityContext.runAsNonRoot=true or carry a documented exception", [input.kind, workload_name])
}

deny contains msg if {
  pod := pod_spec(input)
  workload_name := object.get(object.get(input, "metadata", {}), "name", "")
  some container in object.get(pod, "containers", [])
  object.get(object.get(container, "securityContext", {}), "allowPrivilegeEscalation", true) != false
  msg := sprintf("%s %s container %s must set securityContext.allowPrivilegeEscalation=false", [input.kind, workload_name, object.get(container, "name", "unnamed")])
}

deny contains msg if {
  pod := pod_spec(input)
  workload_name := object.get(object.get(input, "metadata", {}), "name", "")
  some container in object.get(pod, "initContainers", [])
  object.get(object.get(container, "securityContext", {}), "allowPrivilegeEscalation", true) != false
  msg := sprintf("%s %s initContainer %s must set securityContext.allowPrivilegeEscalation=false", [input.kind, workload_name, object.get(container, "name", "unnamed")])
}

deny contains msg if {
  input.kind == "Service"
  service_name := object.get(object.get(input, "metadata", {}), "name", "")
  service_type := object.get(object.get(input, "spec", {}), "type", "ClusterIP")
  public_service_type(service_type)
  not public_service_exception(service_name, service_type)
  msg := sprintf("Service %s uses public type %s without a documented allowlist entry", [service_name, service_type])
}

deny contains msg if {
  input.kind == "Service"
  service_name := object.get(object.get(input, "metadata", {}), "name", "")
  service_type := object.get(object.get(input, "spec", {}), "type", "ClusterIP")
  public_service_type(service_type)
  some port_spec in object.get(object.get(input, "spec", {}), "ports", [])
  port := object.get(port_spec, "port", -1)
  not public_service_port_exception(service_name, service_type, port)
  msg := sprintf("Service %s exposes disallowed public port %v for type %s", [service_name, port, service_type])
}

deny contains msg if {
  input.kind == "Service"
  service_name := object.get(object.get(input, "metadata", {}), "name", "")
  annotations := object.get(object.get(input, "metadata", {}), "annotations", {})
  object.get(annotations, "service.beta.kubernetes.io/aws-load-balancer-scheme", "") == "internet-facing"
  not internet_facing_service_exception(service_name)
  msg := sprintf("Service %s exposes an internet-facing load balancer without a documented allowlist entry", [service_name])
}

pod_spec(resource) = spec if {
  resource.kind == "Deployment"
  spec := object.get(object.get(object.get(resource, "spec", {}), "template", {}), "spec", {})
}

pod_spec(resource) = spec if {
  resource.kind == "DaemonSet"
  spec := object.get(object.get(object.get(resource, "spec", {}), "template", {}), "spec", {})
}

pod_spec(resource) = spec if {
  resource.kind == "StatefulSet"
  spec := object.get(object.get(object.get(resource, "spec", {}), "template", {}), "spec", {})
}

pod_spec(resource) = spec if {
  resource.kind == "Job"
  spec := object.get(object.get(object.get(resource, "spec", {}), "template", {}), "spec", {})
}

pod_spec(resource) = spec if {
  resource.kind == "CronJob"
  spec := object.get(object.get(object.get(object.get(object.get(resource, "spec", {}), "jobTemplate", {}), "spec", {}), "template", {}), "spec", {})
}

pod_runs_as_non_root(pod) if {
  security_context := object.get(pod, "securityContext", {})
  object.get(security_context, "runAsNonRoot", false) == true
}

public_service_type(service_type) if {
  service_type == "LoadBalancer"
}

public_service_type(service_type) if {
  service_type == "NodePort"
}

run_as_non_root_exception(kind, resource_name) if {
  some exception in data.exceptions.kubernetes.run_as_non_root_workloads
  exception.resource_name == resource_name
  some allowed_kind in object.get(exception, "kinds", [])
  allowed_kind == kind
  exception_active(exception)
}

public_service_exception(resource_name, service_type) if {
  some exception in data.exceptions.kubernetes.public_services
  exception.resource_name == resource_name
  some allowed_type in object.get(exception, "service_types", [])
  allowed_type == service_type
  exception_active(exception)
}

public_service_port_exception(resource_name, service_type, port) if {
  some exception in data.exceptions.kubernetes.public_services
  exception.resource_name == resource_name
  some allowed_type in object.get(exception, "service_types", [])
  allowed_type == service_type
  some allowed_port in object.get(exception, "allowed_ports", [])
  allowed_port == port
  exception_active(exception)
}

internet_facing_service_exception(resource_name) if {
  some exception in data.exceptions.kubernetes.public_services
  exception.resource_name == resource_name
  object.get(exception, "allow_internet_facing", false) == true
  exception_active(exception)
}

exception_active(exception) if {
  object.get(exception, "expires_on", "") == ""
}

exception_active(exception) if {
  expires_on := object.get(exception, "expires_on", "")
  expires_on != ""
  time.now_ns() <= time.parse_rfc3339_ns(sprintf("%sT00:00:00Z", [expires_on]))
}