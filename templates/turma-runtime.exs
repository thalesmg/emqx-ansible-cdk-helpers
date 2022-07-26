import Config

config Turma.Decurio,
  inventory: %{
    {% for replicant in (groups["replicants"] | default([]))  %}
      "{{ replicant }}:19876" => ["replicant", "emqx"],
    {% endfor %}
    {% for core in (groups["cores"] | default([]))  %}
      "{{ core }}:19876" => ["core", "emqx"],
    {% endfor %}
    {% for lg in (groups["loadgen"] | default([]))  %}
      "{{ lg }}:19876" => ["loadgen"],
    {% endfor %}
  },
  name: "decurio-{{ inventory_hostname_short }}"

config Turma.Legionarius,
  bind: {"0.0.0.0", 19876},
  subscriptions: [
    {% if "loadgen" in group_names %}
    "loadgen",
    {% endif %}
    {% if "cores" in group_names %}
    "core",
    {% endif %}
    {% if "replicants" in group_names %}
    "replicant",
    {% endif %}
    {% if "emqx" in group_names %}
    "emqx",
    {% endif %}
  ]
