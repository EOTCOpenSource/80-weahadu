
import json
import os
from collections import OrderedDict

def reorder_json_fields():
    folder_path = 'data/am'
    files = sorted(os.listdir(folder_path))

    for file_name in files:
        if file_name.endswith('.json'):
            file_path = os.path.join(folder_path, file_name)
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f, object_pairs_hook=OrderedDict)
                
                if 'testament' in data:
                    testament_value = data.pop('testament')
                    
                    new_data = OrderedDict()
                    for key, value in data.items():
                        new_data[key] = value
                        if key == 'book_short_name_en':
                            new_data['testament'] = testament_value
                    
                    # If chapters is the last key, it will be re-inserted at the end
                    if 'chapters' in new_data:
                        chapters_value = new_data.pop('chapters')
                        new_data['chapters'] = chapters_value

                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(new_data, f, ensure_ascii=False, indent=4)
                        
                    print(f"Reordered fields in {file_name}")

            except json.JSONDecodeError:
                print(f"Could not decode JSON from {file_name}")
            except Exception as e:
                print(f"An error occurred with {file_name}: {e}")

if __name__ == '__main__':
    reorder_json_fields()
