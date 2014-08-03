import json
import console_helper
import os.path

def load_json(filename):
    console_helper.echo_info("loading configuration {0}...".format(filename))

    f = open(filename, "r")
    loaded_json = json.load(f)
    f.close()

    return loaded_json

def load_json_in_dirs(filename, dirs):
    for dir_candidate in dirs:
        file_path = dir_candidate + '/' + filename
        if os.path.exists(file_path):
            return load_json(file_path)
    console_helper.echo_error("profile {0} not found...".format(filename))
    return None