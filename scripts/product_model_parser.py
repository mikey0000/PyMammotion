import json


def load_json_from_file(file_path):
    with open(file_path) as file:
        return json.load(file)

json_file_path = 'models_2.json'

# Assuming new_data is the JSON string you provided
new_data = """
{
  "deviceMode": [
    {
      "intMod": "HM010060LBAWD10",
      "extMod": "LubaAWD1000",
      "cutter_height_min": 30,
      "cutter_height_max": 70,
      "working_speed_min": 0.2,
      "working_speed_max": 0.6,
      "work_area_num_max": 3,
      "working_pathSpace_min": 20,
      "working_pathSpace_max": 35,
      "display_imge_type": 1
    },
    // ... other entries ...
  ]
}
"""

# Parse the JSON data
data = load_json_from_file(json_file_path)

inner_list = {}

# Update the inner_list with new data
for item in data['deviceMode']:
    int_mod = item['intMod']

    # Convert keys for compatibility if necessary
    updated_item = {
        "extMod": item["extMod"],
        "cutter_height_min": item["cutter_height_min"],
        "cutter_height_max": item["cutter_height_max"],
        "working_speed_min": item["working_speed_min"],
        "working_speed_max": item["working_speed_max"],
        "work_area_num_max": item["work_area_num_max"],
        "working_path_min": item.get("working_pathSpace_min", 20),
        "working_path_max": item.get("working_pathSpace_max", 35),
        "display_imge_type": item["display_imge_type"]
    }

    # Update existing entry or add a new one
    inner_list[int_mod] = updated_item

# Output updated inner_list
print(inner_list)
