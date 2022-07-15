from ansible.plugins.inventory import BaseInventoryPlugin

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

        inventory.add_group("emqx")
        inventory.add_group("cores")
        inventory.add_group("replicants")
        for i in range(num_emqx):
            group = "cores" if i < num_cores else "replicants"
            inventory.add_host(f"emqx-{i}.int.{cluster_name}", group=group)
            inventory.add_host(f"emqx-{i}.int.{cluster_name}", group="emqx")

        inventory.add_group("loadgen")
        for i in range(num_loadgen):
            inventory.add_host(f"loadgen-{i}.int.{cluster_name}", group="loadgen")
