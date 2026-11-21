const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');

async function smoke() {
  const browser = await chromium.launch({
    executablePath: '/usr/bin/chromium',
    headless: true,
    args: ['--no-sandbox'],
  });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    const base = process.env.ETCS_SMOKE_BASE_URL;
    await context.addCookies([{
      name: 'sessionid',
      value: fs.readFileSync(process.env.ETCS_SMOKE_SESSION, 'utf8'),
      url: base,
    }]);
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(base + '/');
    await page.getByRole('heading', { name: 'نادي هندسة الحاسوب' }).waitFor();
    assert.equal(await page.locator('.workspace-nav a').count(), 5);
    await page.screenshot({ path: process.env.ETCS_SMOKE_ARTIFACTS + '/desktop.png' });

    await page.setViewportSize({ width: 360, height: 800 });
    await page.getByRole('link', { name: 'فعالية وجاهية جديدة' }).click();
    await page.locator('#id_title').fill('المهارات الحياتية لسوق العمل');
    await page.locator('#id_description').fill('وصف النشاط الذي يرسله النادي');
    await page.locator('#id_date').fill(new Date(Date.now() + 7 * 86400000).toISOString().slice(0, 10));
    assert.notEqual(await page.locator('#weekday').innerText(), 'يُحدد من التاريخ');
    await page.locator('#id_venue').fill('قاعة الكلية');
    await page.locator('#id_needs-0-item').fill('عصير');
    await page.locator('#id_needs-0-quantity').fill('100');
    await page.getByRole('button', { name: 'إضافة صنف' }).click();
    await page.locator('#id_needs-1-item').fill('كاسات كرتون');
    await page.locator('#id_needs-1-quantity').fill('60');
    assert.equal(await page.locator('[name$="price"]').count(), 0);
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({ path: process.env.ETCS_SMOKE_ARTIFACTS + '/mobile.png', fullPage: true });
    await page.getByRole('button', { name: 'حفظ ومتابعة إلى المطبوعات والإرسال' }).click();
    await page.waitForURL(/\/requests\/[a-f0-9-]+\/$/);

    await page.locator('#print-file').setInputFiles({
      name: 'poster.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from('%PDF-1.4\nSynthetic printable document'),
    });
    await page.locator('#print-description').fill('اطبع 60 نسخة');
    await page.getByRole('button', { name: 'إضافة الملف' }).click();
    await page.getByText('اطبع 60 نسخة').waitFor();
    await page.getByRole('button', { name: 'إرسال الطلب للمراجعة' }).click();
    await page.getByText('بانتظار المراجعة', { exact: true }).waitFor();
    await page.getByRole('link', { name: 'تقويم الأنشطة' }).click();
    assert.equal(await page.getByText('المهارات الحياتية لسوق العمل').count(), 0);
    assert.deepEqual(errors, []);
    console.log('PASS: desktop and mobile RTL, automatic weekday, two needs without prices, printing attachment and description, submission, pending activity hidden from calendar.');
  } finally {
    await browser.close();
  }
}

smoke().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
