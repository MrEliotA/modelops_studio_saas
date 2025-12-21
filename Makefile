OBS_NAMESPACE ?= monitoring
SHELL := /bin/bash

KIND_CLUSTER ?= modelops-pro
NAMESPACE ?= modelops-system

.PHONY: kind-up kind-down images deploy seed demo port-forward logs

kind-up:
	./deploy/scripts/kind_up.sh $(KIND_CLUSTER)

kind-down:
	kind delete cluster --name $(KIND_CLUSTER) || true

images:
	./deploy/scripts/build_and_load_images.sh $(KIND_CLUSTER)

deploy:
	./deploy/scripts/deploy.sh $(NAMESPACE)

seed:
	./deploy/scripts/seed.sh $(NAMESPACE)

demo:
	./deploy/scripts/demo.sh $(NAMESPACE)

port-forward:
	kubectl -n $(NAMESPACE) port-forward svc/modelops-api 8000:80

logs:
	kubectl -n $(NAMESPACE) logs deploy/modelops-api -f

.PHONY: prod-deploy keda-install keda-apply keda-kind obs-install

prod-deploy:
	./deploy/scripts/deploy_prod.sh $(NAMESPACE)

keda-install:
	./deploy/addons/keda/install_keda.sh

keda-apply:
	kubectl -n $(NAMESPACE) apply -f deploy/addons/keda/scaledobjects/api-cpu.yaml
	kubectl -n $(NAMESPACE) apply -f deploy/addons/keda/scaledobjects/controller-cpu.yaml
	kubectl -n $(NAMESPACE) apply -f deploy/addons/keda/scaledobjects/agent-cpu.yaml

keda-kind:
	./deploy/addons/keda/install_metrics_server_kind.sh
	./deploy/addons/keda/install_keda.sh
	$(MAKE) keda-apply NAMESPACE=$(NAMESPACE)

obs-install:
	./deploy/addons/observability/install_kube_prometheus_stack.sh

obs-install:
	./deploy/addons/observability/install_kube_prometheus_stack.sh

obs-dashboards:
	./deploy/addons/observability/apply_dashboards.sh $(OBS_NAMESPACE)
	kubectl apply -f deploy/addons/observability/k8s/servicemonitors/modelops-services.yaml
