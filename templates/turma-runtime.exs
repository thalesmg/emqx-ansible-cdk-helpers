import Config

config Turma.Decurio,
  inventory: %{
    "emqx" => [
      {% for emqx in (groups["emqx"] | default([]))  %}
      "{{ emqx }}:19876",
      {% endfor %}
    ],
    "core" => [
      {% for core in (groups["cores"] | default([]))  %}
      "{{ core }}:19876",
      {% endfor %}
    ],
    "replicant" => [
      {% for replicant in (groups["replicants"] | default([]))  %}
      "{{ replicant }}:19876",
      {% endfor %}
    ],
    "loadgen" => [
      {% for loadgen in (groups["loadgen"] | default([]))  %}
      "{{ loadgen }}:19876",
      {% endfor %}
    ],
  },
  name: "decurio-{{ inventory_hostname_short }}"

config Turma.Legionarius,
  bind: {"{{ ansible_default_ipv4.address }}", 19876},
  id: "{{ inventory_hostname }}:19876"
