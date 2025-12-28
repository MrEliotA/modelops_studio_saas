"""KFP-003 Classic Train

    Pipeline sources are intentionally small. The runtime artifact is IR YAML.
    """

    from kfp import dsl, components

    dq_check_op = components.load_component_from_file("pipelines/kfp/components/quality/dq_check/component.yaml")
    train_op = components.load_component_from_file("pipelines/kfp/components/train/train_tabular/component.yaml")
    eval_op = components.load_component_from_file("pipelines/kfp/components/eval/evaluate_metrics/component.yaml")
    register_op = components.load_component_from_file("pipelines/kfp/components/registry/register_model/component.yaml")
    deploy_staging_op = components.load_component_from_file("pipelines/kfp/components/deploy/deploy_staging/component.yaml")
    smoke_test_op = components.load_component_from_file("pipelines/kfp/components/deploy/smoke_test/component.yaml")
    approval_op = components.load_component_from_file("pipelines/kfp/components/deploy/manual_approval_gate/component.yaml")
    promote_op = components.load_component_from_file("pipelines/kfp/components/deploy/promote_prod/component.yaml")
    opencost_pull_op = components.load_component_from_file("pipelines/kfp/components/finops/opencost_pull/component.yaml")
    invoice_preview_op = components.load_component_from_file("pipelines/kfp/components/finops/invoice_preview/component.yaml")

    @dsl.pipeline(name="kfp-003-classic-train")
def classic_train_pipeline(
    dataset_uri: str,
    label_col: str,
    algorithm: str = "xgboost",
    acceptance_metric: str = "rmse",
    threshold: float = 0.8,
    registry_group: str = "default",
):
    train_task = train_op(
        **{
            "Dataset URI": dataset_uri,
            "Label column": label_col,
            "Algorithm": algorithm,
        }
    )
    eval_task = eval_op(
        **{
            "Metrics in": train_task.outputs["Training metrics"],
            "Acceptance metric": acceptance_metric,
            "Threshold": threshold,
        }
    )
    with dsl.Condition(eval_task.outputs["Decision"].contains('"passed": true')):
        _ = register_op(
            **{
                "Model artifact": train_task.outputs["Model artifact"],
                "Metrics": train_task.outputs["Training metrics"],
                "Registry group": registry_group,
            }
        )

