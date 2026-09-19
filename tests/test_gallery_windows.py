import copy
import json
import unittest
from unittest.mock import patch
from PIL import Image
from app import create_app
from storage import save_json
import test_operator_tools


class GalleryWindowsTests(unittest.TestCase):
    setUp=test_operator_tools.OperatorToolsTests.setUp
    tearDown=test_operator_tools.OperatorToolsTests.tearDown
    engine=test_operator_tools.OperatorToolsTests.engine
    completed=test_operator_tools.OperatorToolsTests.completed

    def test_thumbnail_display_cache_and_bounded_slideshow_payload(self):
        e,_=self.engine(start=False);source=self.completed(e)
        Image.new('RGB',(3000,2000),'green').save(source/'A01.jpg')
        client=create_app(e).test_client()
        url='/slideshow/photos/'+source.name+'/A01.jpg'
        with client.get(url+'?size=thumb') as thumb:
            self.assertIn('max-age=86400',thumb.headers['Cache-Control']);etag=thumb.headers['ETag']
        with Image.open(e.gallery.image(source.name,'A01.jpg','thumb')) as im:self.assertEqual(im.size,(480,320))
        with Image.open(e.gallery.image(source.name,'A01.jpg')) as im:self.assertEqual(im.size,(1920,1280))
        with client.get(url+'?size=thumb',headers={'If-None-Match':etag}) as unchanged:self.assertEqual(unchanged.status_code,304)
        data=client.get('/api/slideshow').get_json()
        self.assertEqual(data['total'],16);self.assertEqual(len(data['neighbors']),2);self.assertNotIn('photos',data)
        next_data=client.get('/api/slideshow',query_string={'current':data['photo']['id'],'move':'1'}).get_json()
        previous=client.get('/api/slideshow',query_string={'current':next_data['photo']['id'],'move':'-1'}).get_json()
        self.assertEqual(data['photo'],previous['photo'])
        self.assertEqual(client.get(url+'?size=giant').status_code,404)

    def test_pages_bound_dom_and_exclude_held_and_discover_new_sessions(self):
        e,_=self.engine(start=False);source=self.completed(e)
        for i in range(10):
            ident='batch-'+f'{i:032x}';directory=e.root/'batches'/ident;directory.mkdir()
            save_json(directory/'manifest.json',{'id':ident,'stage':'complete' if i<9 else 'capture_held','completed_at':i+2})
            Image.new('RGB',(400,300),'blue').save(directory/'sheet.png')
        client=create_app(e).test_client();page=client.get('/photos').get_data(as_text=True)
        self.assertEqual(page.count('class="session"'),3)
        self.assertNotIn('batch-'+f'{9:032x}'+'/sheet.png',page)
        self.assertEqual(client.get('/photos?page=2').get_data(as_text=True).count('class="session"'),3)
        self.assertIn('Finished four-strip sheet',client.get('/photos?source=sheets').get_data(as_text=True))
        self.assertEqual(client.get('/photos?page=-1').status_code,400)
        settings={'source':'sheets','seconds':5,'shuffle_all':True}
        before=e.gallery.window(settings,seed='stable');current=before['photo']['id']
        e.gallery.next_refresh=0
        self.assertEqual(e.gallery.window(settings,current=current,seed='stable')['photo']['id'],current)

    def test_scan_reference_preview_link_exists_without_printing(self):
        e,cards=self.engine(start=False);e.phase='watching'
        record=e.calibration_print.prepare(scan=True)
        client=create_app(e).test_client()
        self.assertEqual(client.get(record['url']).status_code,200)
        self.assertEqual(sum(c.shutters for c in cards.values()),0)
