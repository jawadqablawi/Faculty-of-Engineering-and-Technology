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
    await page.getByRole('button', { name: 'طي القائمة' }).click();
    assert(await page.locator('.layout').evaluate(element => element.classList.contains('sidebar-collapsed')));
    await page.reload();
    await page.getByRole('button', { name: 'توسيع القائمة' }).click();
    await page.screenshot({ path: process.env.ETCS_SMOKE_ARTIFACTS + '/desktop.png' });

    await page.setViewportSize({ width: 360, height: 800 });
    const openDrawer = page.getByRole('button', { name: 'فتح القائمة' });
    await openDrawer.click();
    assert(await page.getByRole('dialog', { name: 'القائمة' }).isVisible());
    await page.keyboard.press('Escape');
    assert(await openDrawer.evaluate(element => document.activeElement === element));
    await openDrawer.click();
    await page.getByRole('link', { name: 'فعالية وجاهية جديدة' }).click();
    assert.equal(await page.getByRole('navigation', { name: 'مسار الصفحة' }).locator('[aria-current]').textContent(), 'فعالية وجاهية جديدة');
    const nextStep = page.getByRole('button', { name: 'التالي: الاحتياجات' });
    await nextStep.click();
    await page.getByText('هذا الحقل مطلوب.').first().waitFor();
    await page.locator('#id_title').fill('المهارات الحياتية لسوق العمل');
    await page.getByText('هناك تغييرات غير محفوظة.').waitFor();
    assert(await page.evaluate(() => {
      const event = new Event('beforeunload', {cancelable: true});
      window.dispatchEvent(event);
      return event.defaultPrevented;
    }));
    await page.locator('#id_description').fill('وصف النشاط الذي يرسله النادي');
    await page.locator('#id_date').fill(new Date(Date.now() + 7 * 86400000).toISOString().slice(0, 10));
    assert.notEqual(await page.locator('#weekday').innerText(), 'يُحدد من التاريخ');
    await page.locator('#id_venue').fill('قاعة الكلية');
    await nextStep.click();
    assert.match(await page.locator('.request-stepper [aria-current]').innerText(), /٢\s+الاحتياجات/);
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
    assert.match(await page.locator('.request-stepper [aria-current]').innerText(), /المطبوعات/);

    await page.locator('#print-file').setInputFiles({
      name: 'poster.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from('%PDF-1.4\nSynthetic printable document'),
    });
    await page.locator('#print-description').fill('اطبع 60 نسخة');
    await page.getByRole('button', { name: 'إضافة الملف' }).click();
    await page.getByText('اطبع 60 نسخة').waitFor();
    const deleteFile = page.getByRole('button', { name: 'إزالة الملف' });
    await deleteFile.click();
    const confirmation = page.getByRole('dialog', { name: 'تأكيد الإجراء' });
    await confirmation.waitFor();
    assert(await confirmation.getByText('إزالة هذا المرفق؟').isVisible());
    await confirmation.getByRole('button', { name: 'رجوع' }).click();
    assert(await page.getByText('اطبع 60 نسخة').isVisible());
    await page.getByRole('button', { name: 'إرسال الطلب للمراجعة' }).click();
    await page.getByText('بانتظار المراجعة', { exact: true }).waitFor();
    assert.match(await page.locator('.tracking-steps [aria-current]').innerText(), /المراجعة/);
    const details = page.locator('#request-details');
    assert(!(await details.evaluate(node => node.open)));
    await page.getByText('عرض تفاصيل الطلب', { exact: true }).click();
    assert(await details.evaluate(node => node.open));
    assert(await details.getByText('قاعة الكلية', { exact: false }).first().isVisible());
    const themeToggle = page.locator('[data-theme-toggle]');
    const themeBefore = await page.locator('html').getAttribute('data-theme');
    await themeToggle.click();
    assert.notEqual(await page.locator('html').getAttribute('data-theme'), themeBefore);
    assert(await page.locator('.request-tracking').isVisible());
    await themeToggle.click();
    await page.getByText('عرض تفاصيل الطلب', { exact: true }).click();
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.getByRole('searchbox', { name: 'ابحث في الطلبات' }).fill('المهارات الحياتية');
    await page.getByRole('search', { name: '' }).getByRole('button', { name: 'بحث' }).click();
    await page.getByRole('link', { name: 'عرض الطلب ←' }).first().waitFor();
    const gridSearch = page.locator('[data-grid-form] [name="q"]');
    await page.route('**/requests/?*', async route => {
      if (route.request().resourceType() === 'fetch') {
        await new Promise(resolve => setTimeout(resolve, 220));
      }
      await route.continue();
    });
    await gridSearch.fill('عنوان لا يطابق');
    await page.locator('.table-skeleton').waitFor({ state: 'visible' });
    await page.getByText('لم نجد طلبات تطابق البحث.').waitFor();
    await gridSearch.fill('المهارات الحياتية');
    await page.getByRole('link', { name: 'عرض الطلب ←' }).first().waitFor();
    assert(await page.locator('.mobile-cell-label').first().isVisible());
    const narrow = await page.locator('.responsive-table tbody tr').first().evaluate(row => getComputedStyle(row).display);
    assert.equal(narrow, 'block');
    await page.locator('[data-grid-form] [name="sort"]').selectOption('title');
    await page.waitForURL(/sort=title/);
    await page.unroute('**/requests/?*');
    await page.getByLabel('ملف المستخدم').click();
    assert(await page.getByRole('button', { name: 'خروج' }).isVisible());
    await page.keyboard.press('Escape');
    assert(!(await page.getByRole('button', { name: 'خروج' }).isVisible()));
    await openDrawer.click();
    await page.getByRole('link', { name: 'تقويم الأنشطة' }).click();
    assert.equal(await page.getByText('المهارات الحياتية لسوق العمل').count(), 0);
    const mode = page.getByLabel('الفترة المعروضة');
    await mode.selectOption('week');
    assert.equal(await page.locator('#calendar-grid .calendar-cell').count(), 7);
    await mode.selectOption('day');
    assert.equal(await page.locator('#calendar-grid .calendar-cell').count(), 1);
    await page.getByRole('button', { name: /فعالية معتمدة للاختبار/ }).click();
    await page.getByRole('dialog', { name: 'فعالية معتمدة للاختبار' }).waitFor();
    await page.getByText('تعارض محتمل في المكان.').waitFor();
    await page.keyboard.press('Escape');
    assert(!(await page.getByRole('dialog', { name: 'فعالية معتمدة للاختبار' }).isVisible()));
    const foreignConflict = page.waitForResponse(response => response.url().includes('event_conflict='));
    await page.getByRole('button', { name: /حجز متزامن للاختبار/ }).click();
    assert.deepEqual(await (await foreignConflict).json(), {conflict: null});
    await page.keyboard.press('Escape');
    await page.keyboard.press('/');
    assert(await page.locator('#workspace-search').evaluate(input => document.activeElement === input));
    await page.locator('[data-notification-menu] summary').click();
    await page.getByText('إشعار اختباري ثانٍ').waitFor();
    const notificationURL = page.url();
    const unreadBefore = Number(await page.locator('[data-unread-count]').textContent());
    await page.getByRole('button', { name: 'تحديد كمقروء', exact: true }).first().click();
    await page.getByText('تم تحديث حالة الإشعارات.').waitFor();
    assert.equal(page.url(), notificationURL);
    assert.equal(Number(await page.locator('[data-unread-count]').textContent()), unreadBefore - 1);
    await page.getByRole('link', { name: 'عرض كل الإشعارات' }).click();
    await page.getByRole('heading', { name: 'الإشعارات' }).waitFor();
    await page.getByRole('button', { name: 'تحديد الكل كمقروء' }).click();
    await page.locator('[data-unread-count]').waitFor({ state: 'hidden' });
    assert(!await page.locator('main [data-unread]').count());
    await page.getByLabel('ملف المستخدم').click();
    await page.getByLabel('تفعيل اختصار البحث (/)').uncheck();
    await page.keyboard.press('Escape');
    await page.keyboard.press('/');
    assert(!(await page.locator('#workspace-search').evaluate(input => document.activeElement === input)));
    await page.getByRole('main').getByRole('link', { name: 'إعدادات إشعارات الجوال' }).click();
    await page.getByRole('heading', { name: 'إشعارات الجوال' }).waitFor();
    await page.getByText(/إشعارات الجوال غير مهيّأة|المتصفح لا يدعم إشعارات الجوال|الإشعارات محظورة من المتصفح/).waitFor();
    const workerPath = await page.evaluate(async () => new URL((await navigator.serviceWorker.ready).active.scriptURL).pathname);
    assert.equal(workerPath, '/sw.js');
    assert.equal(await page.locator('link[rel="manifest"]').getAttribute('href'), '/manifest.webmanifest');
    await page.goBack();
    await page.emulateMedia({ media: 'print', reducedMotion: 'reduce' });
    assert(!(await page.locator('.site-header').isVisible()));
    assert(!(await page.locator('[data-notification-form]').first().isVisible()));

    const guest = await browser.newPage({ viewport: { width: 360, height: 800 } });
    guest.on('pageerror', error => errors.push(error.message));
    await guest.goto(base + '/login/');
    await guest.locator('#id_username').fill('browser@example.test');
    await guest.locator('#id_password').fill('invalid-synthetic-password');
    const passwordToggle = guest.locator('[data-password-toggle]');
    await passwordToggle.click();
    assert.equal(await guest.locator('#id_password').getAttribute('type'), 'text');
    await passwordToggle.click();
    assert.equal(await guest.locator('#id_password').getAttribute('type'), 'password');
    await guest.locator('form[data-account-form]').evaluate(form => {
      form.addEventListener('submit', () => {
        const button = form.querySelector('[type="submit"]');
        const spinner = form.querySelector('.submit-spinner');
        sessionStorage.setItem('spinner-observed', String(button.disabled && !spinner.hidden));
      });
    });
    await guest.getByRole('button', { name: 'دخول إلى مساحة العمل' }).click();
    await guest.getByRole('alert').waitFor();
    assert.equal(await guest.evaluate(() => sessionStorage.getItem('spinner-observed')), 'true');
    await guest.getByRole('link', { name: 'نسيت كلمة المرور؟' }).click();
    assert(await guest.locator('#id_email').isVisible());
    await guest.locator('form[data-account-form]').evaluate(form => { form.noValidate = true; });
    await guest.locator('#id_email').fill('invalid-address');
    await guest.getByRole('button', { name: 'إرسال رابط الاستعادة' }).click();
    await guest.locator('#id_email_error').waitFor();
    await guest.goto(base + '/reset/invalid/invalid/');
    await guest.getByText('رابط إعادة التعيين غير صالح أو انتهت صلاحيته.').waitFor();
    assert.deepEqual(errors, []);
    console.log('PASS: mobile RTL, navigation, tables, request workflow, calendar, confirmation, notifications without reload, shortcut settings, print and authentication.');
  } finally {
    await browser.close();
  }
}

smoke().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
