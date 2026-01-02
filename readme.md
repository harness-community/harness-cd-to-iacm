# harness cd to iacm

create harness iacm workspaces from cd terraform steps

traverse a pipeline's history for rendered terraform plan steps and use the configuration to create workspaces or generate terraform for workspaces

this tool is meant to be ran manually via docker and should be used as a starting point, meaning your custom CD terraform implementation may require slight changes to the code, primary the crafting of the workspace name in the `build_workspace_name` function

this tool does not yet render secrets used in environment or terraform variables

## configuration

configuration is done from a configuration file

```
# prompt for confirmation on every workspace created (requires CREATE_WORKPSACE)
create_workspaces = true

# prompt for confirmation on every workspace created (requires CREATE_WORKPSACE)
interactive = true

[harness]
# target harness endpoint
endpoint = "https://app.harness.io"
# target harness account id
account_id = "AM8HCbDiTXGQNrTIhNl7qQ"
# api key for harness authentication
platform_api_key = "pat.AM8HCbDiTXGQNrTIhNl7qQ.xxx.xxx"
# organization id of target project
org_id = "Modules"
# project id of target project
project_id = "IaCM"
# pipeline identifier to search for history
pipeline_identifier = "legacy_cd_tf_example"
# specify a list of execution identifiers to run (optional)
execution_identifiers = ["VHtLmGk3RyeMmXNqg7rI9A"]

[terraform]
# terraform provisioner to use in iacm
provisioner = "opentofu"
# terraform provisioner version to use in iacm
provisioner_version = "1.8.0"
# tags to add to the workspace (optional)
tags = { created_by = "harness-cd-to-iacm" }
# connectors to add to the workspace (optional)
provider_connectors = [{connector_ref = "account.my_aws_connector",type = "aws"}]
```

you can specify the location of the config file by setting the `CONFIG_FILE` environment variable

## usage

set your configuration file according to above and execute the program:
```shell
docker run --rm -v "$(pwd)/config.toml:/harness/config.toml" -e CONFIG_FILE=/harness/config.toml -it harnesscommunity/harness-cd-to-iacm
```
this command mounts the config file into the container and sets the environment variable to point to it

## extractions

if you have additional dynamic workspace setting you would like to set based on the content of the existing workspace settings, you can pass custom Python functions which take in the default workspace configuration and further modify it as you see fit

```toml
[extractions]
some_extraction = "path.to.my.extraction.function"
```

the function should take in the resulting workspace configuration and return the modified configuration

for example you could create an `extractions.py` in the local directory:
```python
def some_extraction(workspace_config):
    workspace_config["environment_variables"]["MY_VARIABLE"] = {"key": "MY_VARIABLE", "value": "my_value", "value_type": "string"}
    return workspace_config
```

and then add it to the config.toml:
```toml
[extractions]
some_extraction = "extractions.some_extraction"
```

## developemnt notes

secrets are rendered in the detailed execution view (needed to resolve context variables) as `*******` so we have to go back and resolve the pipeline yaml to find the actual secret used

reserch how cd steps store state in secrets and find if we can pull state and push it to iacm workspace after creation
