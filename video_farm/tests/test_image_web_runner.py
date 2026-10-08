"""Exercise native Gemini selection before any prompt or generation submission."""
import re
from unittest.mock import Mock

import pytest

from video_farm.image_web_runner import ImageWebError, NativeImageRun


def native_gemini_run(tmp_path, model, actual_mode, *, available=True):
    run = NativeImageRun({
        "engine": "gemini", "model": model, "aspect_ratio": "1:1",
        "prompt": "A blue cube on a white background", "output_dir": str(tmp_path),
    })
    editor = Mock()
    editor.count.return_value = 1
    editor.is_visible.return_value = True

    def element(label, count=1):
        locator = Mock()
        locator.count.return_value = count
        locator.is_visible.return_value = True
        locator.is_enabled.return_value = True
        locator.get_attribute.return_value = label
        locator.inner_text.return_value = label
        return locator

    selector = element("Open mode picker, current mode: " + actual_mode)
    chip = element("取消选择图片")
    ratio = element("宽高比 1:1")
    menu_names = {
        "gemini-flash": "3.8 Flash 全方位帮助",
        "gemini-flash-lite": "3.5 Flash-Lite 极速回答",
        "gemini-pro": "3.1 Pro 高级推理",
        "gemini-thinking": "Extended thinking Excellent for complex problems",
    }
    item = element(menu_names[model], 1 if available else 0)
    option = element("1:1")

    def by_role(role, name, **kwargs):
        candidates = {
            "button": [("取消选择图片", chip),
                       ("Open mode picker, current mode: " + actual_mode, selector),
                       ("宽高比 1:1", ratio)],
            "menuitem": [(menu_names[model], item)],
            "menuitemradio": [("1:1", option)],
        }.get(role, [])
        for label, locator in candidates:
            if (isinstance(name, re.Pattern) and name.search(label)) or name == label:
                return locator
        return element("", 0)

    page = Mock()
    page.locator.return_value = editor
    page.get_by_role.side_effect = by_role
    run.page = page
    run.guard = Mock()
    run.log = Mock()

    def wait_now(predicate, message, seconds=45):
        if not predicate():
            raise ImageWebError(message)

    run.wait = wait_now
    return run, editor


@pytest.mark.parametrize("actual_mode", ["Flash-Lite", "3.5 Flash-Lite"])
def test_flash_does_not_accept_flash_lite(tmp_path, actual_mode):
    run, editor = native_gemini_run(tmp_path, "gemini-flash", actual_mode)
    with pytest.raises(ImageWebError, match="Gemini 网页模式未确认"):
        run.choose_gemini()
    editor.fill.assert_not_called()
    assert not run.submitted


@pytest.mark.parametrize("model,actual_mode", [
    ("gemini-flash", "Flash"),
    ("gemini-flash", "3.8 Flash"),
    ("gemini-flash-lite", "Flash-Lite"),
    ("gemini-flash-lite", "3.5 Flash-Lite"),
    ("gemini-pro", "Pro"),
    ("gemini-pro", "3.1 Pro"),
    ("gemini-thinking", "扩展思考"),
    ("gemini-thinking", "思考"),
    ("gemini-thinking", "Extended thinking"),
    ("gemini-thinking", "Thinking"),
])
def test_each_gemini_web_mode_is_confirmed(tmp_path, model, actual_mode):
    run, editor = native_gemini_run(tmp_path, model, actual_mode)
    assert run.choose_gemini() is editor
    editor.fill.assert_called_once_with(run.spec["prompt"], timeout=run.control.timeout_ms())
    assert not run.submitted


def test_unavailable_mode_fails_before_prompt_entry(tmp_path):
    run, editor = native_gemini_run(tmp_path, "gemini-pro", "Flash", available=False)
    with pytest.raises(ImageWebError, match="不提供 3.1 Pro"):
        run.choose_gemini()
    editor.fill.assert_not_called()
    assert not run.submitted


def test_invalid_native_download_has_output_error(tmp_path):
    run = NativeImageRun({
        "engine": "gemini", "model": "gemini-flash", "aspect_ratio": "1:1",
        "prompt": "a cube", "output_dir": str(tmp_path),
    })
    run.submitted = True
    download = Mock(suggested_filename="image.png")
    download.save_as.side_effect = lambda name: __import__("pathlib").Path(name).write_bytes(b"broken image")
    with pytest.raises(ImageWebError) as error:
        run.save(download, 1)
    assert error.value.code == "IMAGE_OUTPUT_INVALID"


@pytest.mark.parametrize('loaded,pending', [(False, False), (True, True)])
def test_gemini_reference_must_be_loaded_before_send(tmp_path, loaded, pending):
    run, editor = native_gemini_run(tmp_path, 'gemini-flash', 'Flash')
    editor.press.side_effect = ImageWebError('unsafe send occurred')
    run.spec['reference'] = str(tmp_path/'ref.png')
    run.page.expect_file_chooser = __import__('unittest.mock', fromlist=['MagicMock']).MagicMock()
    composer = Mock()
    images = Mock(); images.count.return_value = 1; images.evaluate_all.return_value = loaded
    progress = Mock(); progress.count.return_value = int(pending)
    composer.locator.side_effect = lambda selector: images if selector == 'img' else progress
    run.page.locator.side_effect = lambda selector: composer if selector == 'input-area-v2' else editor
    with pytest.raises(ImageWebError, match='参考图未加载'):
        run.gemini()
    editor.press.assert_not_called()
    assert not run.submitted


@pytest.mark.parametrize('loaded,pending', [(False, False), (True, True)])
def test_flow_reference_must_be_loaded_before_send(tmp_path, loaded, pending):
    from unittest.mock import MagicMock
    run = NativeImageRun({'engine':'flow', 'model':'nano-pro', 'aspect_ratio':'1:1',
                          'prompt':'a cube', 'output_dir':str(tmp_path), 'reference':'ref.png'})
    run.control = Mock(remaining=0)
    run.control.timeout_ms.return_value = 100
    run.page = MagicMock(); run.guard=Mock(); run.click=Mock(); run.log=Mock()
    composer=Mock(); images=Mock(); images.count.return_value=1; images.evaluate_all.return_value=loaded
    progress=Mock(); progress.count.return_value=int(pending)
    composer.locator.side_effect=lambda selector: images if selector=='img' else progress
    run.page.locator.side_effect=lambda selector: composer if selector=='flow-base-prompt-box' else MagicMock()
    def wait_now(predicate, message, seconds=45):
        if not predicate(): raise ImageWebError(message)
    run.wait=wait_now
    with pytest.raises(ImageWebError, match='参考图未附着'):
        run.attach_flow(Mock())
    assert not run.submitted


def flow_settings_run(tmp_path, *, initial='Select model family', actual='Nano Banana Pro'):
    run = NativeImageRun({'engine':'flow', 'model':'nano-pro', 'aspect_ratio':'1:1',
                          'prompt':'A blue cube', 'output_dir':str(tmp_path), 'project_id':'test-project'})
    state = {'model':initial}
    editor = Mock(); editor.count.return_value=1; editor.is_visible.return_value=True

    def element(label, count=1, attr=None):
        loc=Mock(); loc.count.return_value=count; loc.is_visible.return_value=bool(count)
        loc.is_enabled.return_value=True; loc.get_attribute.return_value=attr or 'true'
        loc.inner_text.return_value=label
        if not count:
            loc.click.side_effect=ImageWebError('model selector disappeared')
        return loc

    selector=element(initial)
    item=element('🍌 Nano Banana Pro')
    def select_model(**kwargs):
        state['model']=actual
        selector.inner_text.return_value=actual
    item.click.side_effect=select_model
    image_mode=element('Image'); aspect=element('1:1'); quantity=element('x1')
    settings=element('Settings trigger'); agent=element('Agent', 0)
    def by_role(role, name=None, **kwargs):
        choices={'button':[('Settings trigger',settings),(state['model'],selector),('Agent',agent)],
                 'radio':[('Image',image_mode),('1:1',aspect),('x1',quantity)],
                 'menuitem':[('🍌 Nano Banana Pro',item)]}.get(role,[])
        for label, loc in choices:
            if (isinstance(name,re.Pattern) and name.search(label)) or name==label:
                return loc
        return element('',0)
    run.page=Mock(); run.page.locator.return_value=editor; run.page.get_by_role.side_effect=by_role
    run.guard=Mock(); run.log=Mock()
    def wait_now(predicate,message,seconds=45):
        if not predicate(): raise ImageWebError(message)
    run.wait=wait_now
    return run,editor


@pytest.mark.parametrize('initial',['Select model family','🍌 Nano Banana 2 Lite'])
def test_flow_model_selector_can_change_accessible_name(tmp_path,initial):
    run,editor=flow_settings_run(tmp_path,initial=initial)
    assert run.choose_flow() is editor
    editor.fill.assert_called_once()
    assert not run.submitted


def test_flow_selected_model_mismatch_cannot_send(tmp_path):
    run,editor=flow_settings_run(tmp_path,actual='Nano Banana 2 Lite')
    with pytest.raises(ImageWebError,match='Flow 模型选择未确认'):
        run.choose_flow()
    editor.fill.assert_not_called()
    assert not run.submitted


def test_flow_selected_model_with_arrow_drop_down_confirmed(tmp_path):
    run,editor=flow_settings_run(tmp_path,actual='🍌 Nano Banana Pro arrow_drop_down')
    assert run.choose_flow() is editor
    editor.fill.assert_called_once()
    assert not run.submitted


def test_flow_model_already_selected_with_multiple_buttons(tmp_path):
    run, editor = flow_settings_run(tmp_path, initial='🍌 Nano Banana Pro arrow_drop_down')
    prev_effect = run.page.get_by_role.side_effect
    def by_role_multi(role, name=None, **kwargs):
        loc = prev_effect(role, name=name, **kwargs)
        if role == 'button' and hasattr(loc, 'inner_text') and 'Nano Banana Pro' in str(loc.inner_text.return_value):
            loc.count.return_value = 2
        return loc
    run.page.get_by_role.side_effect = by_role_multi
    assert run.choose_flow() is editor
    editor.fill.assert_called_once()
    assert not run.submitted
