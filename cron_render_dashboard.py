""" Render the IoT dashboard and commit to git if changed """

import integration_lab_dashboard
import json_generation_lib

working_dir = json_generation_lib.working_dir()
output_file = f"{working_dir}/website/_pages/IoTIntegrationLab.md"
repo = json_generation_lib.get_repo()
# Render the dashboard file
with open("/srv/github-action-scripts/header_iot_int_lab.md", "r") as input_file:
    with open(output_file, "w") as output_file:
        integration_lab_dashboard.render_dashboard(
            ['blueprints/nightly', 'trustedsubstrate/acs-testing'],
            output_file,
            1,
            ['kv260', 'qemu', 'Coorstone-1000', 'Rock5', 'I.MX8.MINI'],
            ['capsule-updates', 'secure-boot-enabled', 'measured-boot', 'filesystem-encryption', 'xtest', 'acs'],
            input_file)
# Did anything change?
json_generation_lib.check_repo_status(repo, "Update IoT Dashboard")
