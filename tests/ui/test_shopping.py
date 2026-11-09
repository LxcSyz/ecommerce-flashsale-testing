import uuid

import pytest
from playwright.sync_api import expect


@pytest.fixture
def shopping_page(page, system):
    page.goto(system[0].base)
    page.get_by_label("用户名", exact=True).fill("ui_" + uuid.uuid4().hex[:12])
    page.get_by_label("密码", exact=True).fill("TestPass123!")
    page.get_by_role("button", name="注册", exact=True).click()
    expect(page.locator("#identity")).to_contain_text("你好")
    return page


def test_checkout_and_mock_payment(shopping_page):
    page = shopping_page
    page.locator('[data-product-id="1"]').get_by_role("button", name="加入购物车").click()
    expect(page.locator("#cart")).to_contain_text("机械键盘 × 1")
    page.get_by_role("button", name="提交订单").click()
    expect(page.locator("#orders")).to_contain_text("¥199.00")
    page.get_by_role("button", name="模拟支付", exact=True).click()
    expect(page.locator("#orders")).to_contain_text("已支付")
    expect(page.locator('[data-product-id="1"] .stock')).to_contain_text("99 / 100")


def test_flash_cancellation_restores_inventory(shopping_page):
    page = shopping_page
    page.get_by_role("button", name="立即抢购").click()
    expect(page.locator("#orders")).to_contain_text("待支付")
    expect(page.locator('[data-product-id="2"] .stock')).to_contain_text("9 / 10")
    page.get_by_role("button", name="取消订单").click()
    expect(page.locator("#orders")).to_contain_text("已取消")
    expect(page.locator('[data-product-id="2"] .stock')).to_contain_text("10 / 10")


def test_anonymous_purchase_requires_login(page, system):
    page.goto(system[0].base)
    page.get_by_role("button", name="立即抢购").click()
    expect(page.get_by_role("status")).to_contain_text("请先登录")
