import json
import logging
from os import getenv

import tomllib
from requests import post

import harness_open_api


logging.basicConfig(level=logging.INFO)

BACKEND_DOCS = "https://developer.harness.io/docs/infra-as-code-management/remote-backends/init-configuration/#set-environment-variables"


def generate_tf(filename: str, workspaces: list[dict]) -> bool:
    """
    Generate terraform for creating workspaces

    Returns: true if file created
    """

    pass


def create_workspace(config: dict, workspace: dict) -> dict:
    """
    Call the harness api to create a workspace

    Returns: response from harness api if successful
    """

    resp = post(
        f"{config['harness']['endpoint']}/iacm/api/orgs/{config['harness']['org_id']}/projects/{config['harness']['project_id']}/workspaces",
        headers={
            "x-api-key": config["harness"]["platform_api_key"],
            "Harness-Account-Id": config["harness"]["account_id"],
        },
        json=workspace,
    )

    try:
        resp.raise_for_status()
    except Exception as e:
        if resp.status_code == 409:
            logging.warning(f"Workspace {workspace['name']} already exists")
            return None
        logging.error(resp.text)
        raise e

    return resp


def convert_variables(payload: str, prefix: str = "") -> dict[str, dict[str, str]]:
    """
    convert variables in a string to workspace variables

    args:
        payload (str): string to convert; format: variable_name = "value"\nvariable_name = "value"

    returns:
        dict[str, dict[str, str]]: iacm workspace variable mappings; format: {"<variable_name>": {"key": "<variable_name>", "value": "<value>", "value_type": "string"}}
    """

    variables = {}
    for variable in payload.split("\n"):
        key, value = variable.split("=")

        key = key.strip()
        value = value.strip()

        # if value has quotes, remove them
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]

        # if value is a secret
        if value.startswith("<+secrets.getValue(") and value.endswith(")>"):
            value = value[20:-3]
            value_type = "secret"
        else:
            value_type = "string"

        variables[prefix + key] = {
            "key": prefix + key,
            "value": value,
            "value_type": value_type,
        }

    return variables


def get_pipeline_yaml(
    api_configuration: harness_open_api.Configuration,
    account_id: str,
    org_id: str,
    project_id: str,
    pipeline_id: str = None,
):
    pipeline_api = harness_open_api.PipelineApi(
        harness_open_api.ApiClient(api_configuration)
    )

    pipeline = pipeline_api.get_pipeline(
        account_id,
        org_id,
        project_id,
        pipeline_id,
    )

    return pipeline.data.yaml_pipeline


def get_pipeline_steps(
    api_configuration: harness_open_api.Configuration,
    account_id: str,
    org_id: str,
    project_id: str,
    step_type: str,
    pipeline_id: str = None,
):
    executions_api = harness_open_api.PipelineExecutionDetailsApi(
        harness_open_api.ApiClient(api_configuration)
    )

    executions = executions_api.get_list_of_executions(
        account_id,
        org_id,
        project_id,
        # workspace=config["executions"].get("workspace", None),
        # pipeline_execution_id=config["executions"].get("pipeline_execution_id", None),
        # status=config["executions"].get("status", None),
        pipeline_identifier=pipeline_id,
        # start_time=config["executions"].get("start_time", None),
        # end_time=config["executions"].get("end_time", None),
        body={"filterType": "PipelineExecution", "pipelineIdentifier": pipeline_id},
    )

    pipeline_execution_details_api = harness_open_api.PipelineExecutionDetailsApi(
        harness_open_api.ApiClient(api_configuration)
    )

    steps = []
    for execution in executions.data.content:
        for stage in execution.layout_node_map:
            details = pipeline_execution_details_api.get_execution_detail_v2(
                account_identifier=config["harness"]["account_id"],
                org_identifier=config["harness"]["org_id"],
                project_identifier=config["harness"]["project_id"],
                plan_execution_id=execution.plan_execution_id,
                stage_node_id=stage,
            )

            for step in details.data.execution_graph.node_map:
                if details.data.execution_graph.node_map[step].step_type == step_type:
                    steps.append(
                        details.data.execution_graph.node_map[step].step_parameters[
                            "spec"
                        ]
                    )

    return steps


def extract_provider_connectors(provider_credential: dict):
    provider_connectors = []
    if provider_credential:
        provider_connectors.append(
            {
                "connector_ref": provider_credential["spec"]["connectorRef"],
                "type": provider_credential["type"].lower(),
            }
        )
    return provider_connectors


def extract_extra_provider_settings(provider_credential: dict):
    """
    For AWS and Azure there are some extra optional setting you can configure on the TFPlan step

    Returns: extra provider settings as environment variables
    """

    extra_provider_settings = {}
    if provider_credential:
        if provider_credential["type"] == "AWS":
            if provider_credential["spec"]["region"]:
                extra_provider_settings["AWS_REGION"] = provider_credential["spec"][
                    "region"
                ]
            if provider_credential["spec"]["roleArn"]:
                extra_provider_settings["AWS_ROLE_ARN"] = provider_credential["spec"][
                    "roleArn"
                ]
        elif provider_credential["type"] == "AZURE":
            if provider_credential["spec"]["subscriptionId"]:
                extra_provider_settings["AZURE_SUBSCRIPTION_ID"] = provider_credential[
                    "spec"
                ]["subscriptionId"]

    return extra_provider_settings


def extract_terraform_variables(var_files: dict):
    """
    Convert inline variables to inline workspace variables
    """

    variables = {}
    for var_file in var_files:
        if var_files[var_file]["type"] == "Inline":
            variables.update(convert_variables(var_files[var_file]["spec"]["content"]))

    return variables


def extract_terraform_variable_files(var_files: dict):
    """
    Convert remote variables to remote workspace variable files
    """

    variable_files = []
    for var_file in var_files:
        # convert remote variables to remote workspace variable files
        if var_files[var_file]["type"] == "Remote":
            # cd allows multiple files where iacm only allows singular
            for file in var_files[var_file]["spec"]["store"]["spec"]["paths"]:
                variable_file = {
                    "repository": var_files[var_file]["spec"]["store"]["spec"][
                        "repoName"
                    ],
                    "repository_connector": var_files[var_file]["spec"]["store"][
                        "spec"
                    ]["connectorRef"],
                    "repository_path": file,
                }

                # iacm also allows repository_sha but cd only allows branch or commit
                if (
                    var_files[var_file]["spec"]["store"]["spec"]["gitFetchType"]
                    == "BRANCH"
                ):
                    variable_file["repository_branch"] = var_files[var_file]["spec"][
                        "store"
                    ]["spec"]["branch"]
                else:
                    variable_file["repository_commit"] = var_files[var_file]["spec"][
                        "store"
                    ]["spec"]["commitId"]
                variable_files.append(variable_file)

    return variable_files


def extract_environment_variables(environment_variables: dict):
    """
    Convert environment variables to inline workspace variables
    """

    environment_variables = {}
    for env_var in environment_variables:
        if environment_variables[env_var].startswith("<+secrets.getValue("):
            environment_variables[env_var] = {
                "key": env_var,
                "value": environment_variables[env_var],
                "value_type": "secret",
            }
        else:
            environment_variables[env_var] = {
                "key": env_var,
                "value": environment_variables[env_var],
                "value_type": "string",
            }

    return environment_variables


## TODO: you should modify this to fit your workspace naming standards based on the information avalible in the execution context
def build_workspace_name(
    config: dict, step: dict, terraform_variables: dict, environment_variables: dict
):
    return (
        config["harness"]["project_id"]
        + "_"
        + terraform_variables.get("environment", {}).get("value", "dev")
        + "_"
        + step["configuration"]["configFiles"]["store"]["spec"]["folderPath"].replace(
            "/", "_"
        )
        + "_"
        + terraform_variables.get("region", {}).get("value", "dev")
    ).lower()


if __name__ == "__main__":
    # save workspaces we have created as to not create duplicates
    created_workspaces = []

    # load in configuration
    with open(getenv("CONFIG_FILE", "config.toml"), "rb") as f:
        config = tomllib.load(f)

    # set up authentication for the sdk
    configuration = harness_open_api.Configuration()
    configuration.api_key["x-api-key"] = config["harness"]["platform_api_key"]

    # resolve all recent executions and extract the terraform plan steps
    steps = get_pipeline_steps(
        configuration,
        config["harness"]["account_id"],
        config["harness"]["org_id"],
        config["harness"]["project_id"],
        config["harness"].get("step_type", "TERRAFORM_PLAN_V2"),
        config["harness"]["pipeline_identifier"],
    )

    for step in steps:
        # generate workspace payload with given converters
        provider_connectors = extract_provider_connectors(
            step["configuration"].get("providerCredential")
        )
        repository_connectors = (
            step["configuration"]["configFiles"]["store"]["spec"]["connectorRef"]
            if step["configuration"]["configFiles"]["store"]["type"] != "HARNESS_CODE"
            else ""
        )
        environment_variables = extract_environment_variables(
            step["configuration"]["environmentVariables"]
        )
        terraform_variables = extract_terraform_variables(
            step["configuration"]["varFiles"]
        )
        terraform_variable_files = extract_terraform_variable_files(
            step["configuration"]["varFiles"]
        )
        tags = config["terraform"].get("tags", {})
        if not isinstance(tags, dict):
            logging.warning("Tags must be a dictionary, will not be used")
            tags = {}

        name = build_workspace_name(
            config, step, terraform_variables, environment_variables
        )
        if name in created_workspaces:
            logging.info(f"Workspace {name} already created")
            continue

        # assemble payload
        workspace_payload = {
            "identifier": name.replace(" ", "_")
            .replace("/", "_")
            .replace(".", "_")
            .replace("-", "_")
            .lower(),
            "name": name.replace(".", "_"),
            "provisioner": config["terraform"]["provisioner"],
            "provisioner_version": config["terraform"]["provisioner_version"],
            "provider_connector": "",
            "provider_connectors": provider_connectors,
            "repository_connector": repository_connectors,
            "repository": step["configuration"]["configFiles"]["store"]["spec"][
                "repoName"
            ],
            "repository_branch": step["configuration"]["configFiles"]["store"][
                "spec"
            ].get("branch", None),
            "repository_commit": step["configuration"]["configFiles"]["store"][
                "spec"
            ].get("commitId", None),
            "repository_path": step["configuration"]["configFiles"]["store"]["spec"][
                "folderPath"
            ],
            "environment_variables": environment_variables,
            "terraform_variables": terraform_variables,
            "terraform_variable_files": terraform_variable_files,
            "tags": tags,
        }

        # add in backend config variables if inline
        if "backendConfig" in step["configuration"]:
            if step["configuration"]["backendConfig"]["type"] == "Inline":
                workspace_payload["environment_variables"].update(
                    convert_variables(
                        step["configuration"]["backendConfig"][
                            "terraformBackendConfigSpec"
                        ]["content"],
                        "PLUGIN_INIT_BACKEND_CONFIG_",
                    )
                )
            else:
                logging.warning(
                    f"!! Backend config is not inline, will not be configured, see {BACKEND_DOCS}"
                )

        # find secret references and try to resolve them
        for variable in workspace_payload["environment_variables"]:
            if (
                workspace_payload["environment_variables"][variable]["value"]
                == "*******"
            ):
                # resolve secret ref from pipeline yaml
                pass
                pipeline = get_pipeline_yaml(
                    configuration,
                    config["harness"]["account_id"],
                    config["harness"]["org_id"],
                    config["harness"]["project_id"],
                    config["harness"]["pipeline_identifier"],
                )
                print(pipeline)

        # show and create workspace
        print(json.dumps(workspace_payload, indent=4))

        if config["create_workspaces"]:
            if config["interactive"]:
                if (
                    input("Do you want to continue? (yes/no): ").lower().strip()
                    != "yes"
                ):
                    continue
            create_workspace(config, workspace_payload)
            created_workspaces.append(name)
