from ansible.plugins.inventory import BaseInventoryPlugin

def _add_jumphost(inventory, host, bastion_server):
    if bastion_server:
        inventory.set_variable(host, 'ansible_ssh_common_args', f"-o StrictHostKeyChecking=no -J ec2-user@{bastion_server}")

class InventoryModule(BaseInventoryPlugin):
    # used internally by Ansible, it should match the file name but not required
    NAME = 'tmginv'

    def verify_file(self, path):
        # print("verify_file", "path", path)
        return True

    def parse(self, inventory, loader, path, cache=True):
        # print("inv", inventory, "load", loader, "path", path, "cache", cache)
        super(InventoryModule, self).parse(inventory, loader, path, cache)
        num_emqx = int(self._vars["emqx_emqx_num"])
        num_cores = int(self._vars["emqx_num_cores"])
        num_loadgen = int(self._vars["emqx_loadgen_num"])
        cluster_name = self._vars["emqx_cluster_name"]
        bastion_server = self._vars.get("emqx_bastion_server")

        inventory.add_group("emqx")
        inventory.add_group("cores")
        inventory.add_group("replicants")
        for i in range(num_emqx):
            group = "cores" if i < num_cores else "replicants"
            host = f"emqx-{i}.int.{cluster_name}"
            inventory.add_host(host, group=group)
            inventory.add_host(host, group="emqx")
            inventory.set_variable(host, "ansible_user", "ubuntu")
            _add_jumphost(inventory, host, bastion_server)

        inventory.add_group("loadgen")
        for i in range(num_loadgen):
            host = f"loadgen-{i}.int.{cluster_name}"
            inventory.add_host(host, group="loadgen")
            inventory.set_variable(host, "ansible_user", "ubuntu")
            _add_jumphost(inventory, host, bastion_server)
