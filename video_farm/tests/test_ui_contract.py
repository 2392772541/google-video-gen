"""Presentation contract regressions; no browser, live DB or paid generation required."""
import json
import re
import unittest
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / 'static'
BASELINE = Path(__file__).parent / 'fixtures/ui_contract_before_rebuild.json'

class PageContract(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.ids=[]; self.hooks=[]; self.inputs={}; self.options={}; self.attrs={}; self.select=None
        self.feed(text)
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if a.get('id'):
            self.ids.append(a['id']); self.attrs[a['id']]=a
        if a.get('onclick'): self.hooks.append(a['onclick'])
        if tag in ('input','textarea','select') and a.get('id'):
            self.inputs[a['id']]={k:a[k] for k in ('name','type','accept','multiple') if k in a}
        if tag=='select': self.select=a.get('id'); self.options.setdefault(self.select,[])
        if tag=='option' and self.select and 'value' in a: self.options[self.select].append(a['value'])
    def handle_endtag(self, tag):
        if tag=='select': self.select=None

class UIContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline=json.loads(BASELINE.read_text('utf-8'))
        cls.pages={name:PageContract((STATIC/name).read_text('utf-8')) for name in cls.baseline}
        cls.css=(STATIC/'studio.css').read_text('utf-8')
        cls.vids=(STATIC/'vids.js').read_text('utf-8')
        cls.app=(STATIC/'app.js').read_text('utf-8')
    def test_original_dom_ids_preserved(self):
        for name,b in self.baseline.items():
            with self.subTest(page=name): self.assertFalse(set(b['ids'])-set(self.pages[name].ids))
    def test_no_duplicate_dom_ids(self):
        for name,p in self.pages.items():
            with self.subTest(page=name): self.assertFalse([id for id,n in Counter(p.ids).items() if n>1])
    def test_original_inline_event_hooks_preserved(self):
        for name,b in self.baseline.items():
            with self.subTest(page=name): self.assertFalse(set(b['hooks'])-set(self.pages[name].hooks))
    def test_form_input_semantics_preserved(self):
        for name,b in self.baseline.items():
            for id,attrs in b['inputs'].items():
                with self.subTest(page=name,control=id): self.assertEqual(attrs,self.pages[name].inputs[id])
    def test_select_option_values_and_order_preserved(self):
        for name,b in self.baseline.items():
            for id,options in b['options'].items():
                if name == "index.html" and id == "select-image-model":
                    options = ["nano-pro", "nano2-lite", "nano2.1"]
                with self.subTest(page=name,control=id): self.assertEqual(options,self.pages[name].options[id])
    def test_advanced_accordion_can_open_and_close(self):
        self.assertNotIn('display:none', self.pages['index.html'].attrs['accordion-body-adv'].get('style','').replace(' ',''))
        self.assertIn('.studio-main .accordion-body{display:none}',self.css)
        self.assertIn('.studio-main .accordion-body.open{display:block}',self.css)
        self.assertIn('el.advBody.classList.add("open")',self.app)
        self.assertIn('el.advBody.classList.remove("open")',self.app)
    def test_export_uses_actual_textarea_id_and_legacy_fallbacks(self):
        self.assertIn('json-export-textarea',self.pages['vids.html'].ids)
        self.assertEqual(3,self.vids.count("getEl('json-export-textarea', 'batch-export-textarea', 'export-json-textarea')"))
        self.assertIn('function getEl(...ids)',self.vids)
    def test_shot_videos_do_not_autoplay(self):
        videos=re.findall(r'<video\b[^>]*>',self.vids)
        self.assertTrue(videos)
        for tag in videos:
            self.assertNotRegex(tag,r'\bautoplay\b')
            self.assertIn('controls',tag)
            self.assertIn('preload="metadata"',tag)
    def test_sidebar_hash_links_match_main_views(self):
        main_ids=set(self.pages['index.html'].ids)
        html=(STATIC/'vids.html').read_text('utf-8')
        targets=re.findall(r'href="/#(view-[a-z]+)"',html)
        self.assertEqual(5,len(targets))
        self.assertTrue(set(targets)<=main_ids)
    def test_presentation_shell_has_no_network_or_task_state(self):
        shell=(STATIC/'studio-shell.js').read_text('utf-8')
        self.assertNotRegex(shell,r'\bfetch\s*\(|XMLHttpRequest|/api/|localStorage|sessionStorage')
        self.assertIn("aria-current",shell)
        self.assertIn("aria-expanded",shell)
    def test_qa_caption_does_not_claim_requested_spec_is_measured(self):
        self.assertNotIn(' · 9:16 竖屏 · 实际生成时长:',self.app)
        self.assertIn('请求画幅:',self.app)
        self.assertIn('请求时长:',self.app)
        self.assertNotIn('watermarkText = "✓ 无水印"',self.app)
        self.assertIn('watermarkText = "✓ 抽查未检出"',self.app)
        self.assertNotIn('SynthID) 保留在像素频域中',self.app)
    def test_shared_assets_have_consistent_cache_versions(self):
        versions=[]
        for name in self.pages:
            html=(STATIC/name).read_text('utf-8')
            versions+=re.findall(r'/static/[^"\s]+\?v=(studio[^"\s]+)',html)
        self.assertTrue(versions)
        self.assertEqual(1,len(set(versions)))

    def test_parameter_setters_sync_pressed_state_after_reset(self):
        self.assertIn('btn.setAttribute("aria-pressed", String(btn.getAttribute("data-aspect") === aspect))', self.app)
        self.assertIn('btn.setAttribute("aria-pressed", String(parseInt(btn.getAttribute("data-sec")) === sec))', self.app)
    def test_player_metadata_is_not_hardcoded_as_clean_portrait(self):
        self.assertNotIn('MP4 H.264 · 纯净成片', self.app)
        self.assertIn('水印状态请查看质检', self.app)

    def test_secondary_pages_have_shrinkable_responsive_layout(self):
        html=(STATIC/'index.html').read_text('utf-8')
        self.assertIn('class="studio-grid image-studio-grid"',html)
        self.assertNotIn('grid-template-columns:420px 1fr',html)
        self.assertIn('#view-images .image-studio-grid{grid-template-columns:minmax(0,1fr)}',self.css)
        self.assertIn('.studio-main .filter-group{flex-wrap:wrap;min-width:0}',self.css)

if __name__=='__main__': unittest.main()
