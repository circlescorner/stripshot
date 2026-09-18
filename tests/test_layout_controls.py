import copy
import io
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from app import create_app
from render import render_sheet, validate_layout
import test_software_app


class LayoutControlsTests(unittest.TestCase):
    setUp = test_software_app.SoftwareAppTests.setUp
    tearDown = test_software_app.SoftwareAppTests.tearDown
    engine = test_software_app.SoftwareAppTests.engine

    def test_layout_api_persists_and_does_not_change_frozen_batch(self):
        e,_=self.engine()
        client=create_app(e).test_client()
        token=re.search(rb'name="stripshot-token" content="([^"]+)"',client.get('/').data).group(1).decode()
        layout={'margin':36,'gap':24,'top':36,'bottom':180,'photo_scale':95}
        self.assertEqual(client.post('/api/layout',json=layout).status_code,403)
        self.assertEqual(client.post('/api/layout',json=layout,headers={'X-Stripshot-Token':token}).status_code,200)
        e.stop()
        # Freeze without starting any camera, then edit future layout.
        e.freeze(software=True)
        next_layout={**layout,'margin':48,'photo_scale':90}
        e.action('layout',next_layout)
        self.assertEqual(e.state['current']['layout'],layout)
        restarted,_=self.engine(start=False)
        self.assertEqual(restarted.layout,next_layout)
        self.assertEqual(restarted.state['current']['layout'],layout)
        self.assertEqual(json.loads(e.layout_path.read_text()),next_layout)

    def test_invalid_or_unsaved_layout_never_replaces_current(self):
        e,_=self.engine(start=False)
        original=copy.deepcopy(e.layout)
        for layout in (None,{}, {**original,'margin':300}, {**original,'photo_scale':49}, {**original,'gap':True}):
            with self.assertRaises(ValueError):e.action('layout',layout)
            self.assertEqual(e.layout,original)
        with patch('batch.save_json',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):e.action('layout',{**original,'photo_scale':95})
        self.assertEqual(e.layout,original)

    def test_photo_scaling_centers_in_slot_without_scaling_overlay(self):
        photos={'A':[],'B':[]}
        for c in photos:
            for i in range(8):
                p=self.root/f'{c}{i}.jpg';Image.new('RGB',(150,150),'red').save(p);photos[c].append(p)
        overlay=self.root/'art.png';art=Image.new('RGBA',(600,1800),(0,0,0,0));art.putpixel((20,20),(0,0,255,255));art.save(overlay)
        layout={'margin':50,'gap':0,'top':100,'bottom':100,'photo_scale':80}
        output=self.root/'sheet.png';render_sheet(photos,[overlay]*4,layout,output)
        with Image.open(output) as im:
            self.assertEqual(im.getpixel((20,20)),(0,0,255))
            # Slot 500x400; 80% photo is 400x320, centered at x100,y140.
            self.assertEqual(im.getpixel((99,150)),(255,255,255))
            self.assertGreater(im.getpixel((100,140))[0],240)
            self.assertEqual(im.getpixel((300,139)),(255,255,255))
            self.assertEqual(im.getpixel((500,150)),(255,255,255))
