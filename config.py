import os
import yaml

class ConfigHandler:
    def __init__(self, config_path=None):
        if config_path is None:
            self.config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.yaml')
        else:
            self.config_path = config_path
        self.config = self.load_config()

    def load_config(self):
        """Loads configuration from the YAML file."""
        if not os.path.exists(self.config_path):
            return {}
        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Error loading config: {e}")
            return {}

    def save_config(self):
        """Saves current configuration to the YAML file."""
        try:
            with open(self.config_path, 'w') as f:
                yaml.safe_dump(self.config, f, default_flow_style=False)
        except Exception as e:
            print(f"Error saving config: {e}")

    def get(self, section, key, default=None):
        """Gets a configuration value."""
        return self.config.get(section, {}).get(key, default)

    def set(self, section, key, value):
        """Sets a configuration value and saves the file."""
        if section not in self.config:
            self.config[section] = {}
        self.config[section][key] = value
        self.save_config()
