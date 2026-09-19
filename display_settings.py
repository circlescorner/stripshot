"""Persisted display controls, independent of batch evidence and print intent."""
import copy
import json
from storage import save_json

DEFAULT_DISPLAY = {'seconds':5, 'shuffle_all':False, 'source':'all'}


def validate_display(value):
    if not isinstance(value,dict) or set(value) != set(DEFAULT_DISPLAY):
        raise ValueError('Slideshow needs seconds, shuffle_all and source')
    if type(value['seconds']) not in (int,float) or not 1 <= value['seconds'] <= 120:
        raise ValueError('Slideshow timing must be 1–120 seconds')
    if type(value['shuffle_all']) is not bool or value['source'] not in ('all','latest','sheets'):
        raise ValueError('Choose a slideshow source and a true/false shuffle setting')


class DisplaySettings:
    def initialize_display(self):
        self.display_path = self.root / 'operator-slideshow.json'
        self.display = json.loads(self.display_path.read_text()) if self.display_path.exists() else copy.deepcopy(DEFAULT_DISPLAY)
        validate_display(self.display)

    def save_display(self, candidate):
        validate_display(candidate)
        with self.lock:
            save_json(self.display_path,candidate)
            self.display = copy.deepcopy(candidate)
