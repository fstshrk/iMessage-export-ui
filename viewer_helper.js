/**
 * iMessage Export Viewer Helper
 *
 * Copyright (c) 2026, Bora Akyol
 * All rights reserved.
 * Licensed under the BSD 3-Clause License. See LICENSE for details.
 *
 * - Reverses message order so most current message appears at the top.
 * - Floating navigation bar: Jump to Top, Jump to Bottom, Toggle Order.
 * - Dynamic scroll indicator: Shows current Month & Year while scrolling.
 * - Interactive Timeline Drawer: Quick-jump to any Month & Year.
 */

(function () {
  'use strict';

  let isNewestOnTop = true;
  let messagesList = [];
  let monthMap = new Map(); // "YYYY-MM" -> element
  let monthCounts = new Map(); // "YYYY-MM" -> count
  let scrollTimeout = null;

  // Month names
  const MONTH_NAMES = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
  ];
  const SHORT_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  function init() {
    // Collect all message and announcement elements
    const elements = Array.from(document.querySelectorAll('.message, .announcement'));
    if (elements.length === 0) return;

    messagesList = elements;

    // Scan dates and build month map
    buildMonthIndex();

    // Reorder messages: default newest on top
    if (isNewestOnTop) {
      applyOrder(true);
    }

    // Inject styles and floating UI
    injectUI();

    // Listen to scroll events for dynamic Month/Year pill
    window.addEventListener('scroll', handleScroll, { passive: true });

    // Listen to parent postMessage (from index.html toolbar)
    window.addEventListener('message', handleParentMessage);
  }

  function parseDateFromElement(el) {
    const tsEl = el.querySelector('.timestamp');
    if (!tsEl) return null;
    const text = tsEl.textContent.trim();
    // Format: "Oct 25, 2026 10:16:39 AM"
    const match = text.match(/([A-Za-z]{3})\s+(\d{1,2}),\s+(\d{4})/);
    if (!match) return null;
    const monthIdx = SHORT_MONTHS.indexOf(match[1]);
    if (monthIdx === -1) return null;
    const year = parseInt(match[3], 10);
    const day = parseInt(match[2], 10);
    return {
      year,
      month: monthIdx,
      day,
      key: `${year}-${String(monthIdx + 1).padStart(2, '0')}`,
      label: `${MONTH_NAMES[monthIdx]} ${year}`
    };
  }

  function buildMonthIndex() {
    monthMap.clear();
    monthCounts.clear();

    messagesList.forEach((el) => {
      const parsed = parseDateFromElement(el);
      if (parsed) {
        el.dataset.dateKey = parsed.key;
        el.dataset.dateLabel = parsed.label;
        if (!monthMap.has(parsed.key)) {
          monthMap.set(parsed.key, el);
        }
        monthCounts.set(parsed.key, (monthCounts.get(parsed.key) || 0) + 1);
      }
    });
  }

  function applyOrder(newestOnTop) {
    isNewestOnTop = newestOnTop;
    const body = document.body;

    // Detach elements and re-append in reversed order
    const fragment = document.createDocumentFragment();
    if (newestOnTop) {
      // Elements are naturally oldest-first in HTML, reverse them
      for (let i = messagesList.length - 1; i >= 0; i--) {
        fragment.appendChild(messagesList[i]);
      }
    } else {
      // Restore original chronological order
      for (let i = 0; i < messagesList.length; i++) {
        fragment.appendChild(messagesList[i]);
      }
    }

    // Keep UI container at top
    const uiContainer = document.getElementById('viewer-ui-root');
    body.appendChild(fragment);
    if (uiContainer) {
      body.insertBefore(uiContainer, body.firstChild);
    }

    // Scroll to top
    window.scrollTo(0, 0);

    // Update order button label
    const orderBtn = document.getElementById('btn-toggle-order');
    if (orderBtn) {
      orderBtn.innerHTML = isNewestOnTop ? '⇅ Newest First' : '⇅ Oldest First';
      orderBtn.title = isNewestOnTop ? 'Currently showing newest messages at top. Click for chronological.' : 'Currently showing oldest messages at top. Click for newest first.';
    }

    updateScrollDate();
  }

  function injectUI() {
    const root = document.createElement('div');
    root.id = 'viewer-ui-root';
    root.innerHTML = `
      <!-- Floating Top Navigation -->
      <div class="viewer-nav-bar" id="viewerNavBar">
        <div class="nav-left">
          <button class="nav-btn" id="btn-toggle-order" title="Toggle newest/oldest on top">⇅ Newest First</button>
        </div>
        
        <!-- Date pill -->
        <div class="nav-center">
          <div class="date-pill" id="datePill" title="Click to jump to a specific month/year">
            <span class="date-icon">📅</span>
            <span class="date-text" id="datePillText">Latest</span>
            <span class="date-caret">▾</span>
          </div>
        </div>

        <div class="nav-right">
          <button class="nav-btn" id="btn-scroll-top" title="Go to top">⬆ Top</button>
          <button class="nav-btn" id="btn-scroll-bottom" title="Go to bottom">⬇ Bottom</button>
        </div>
      </div>

      <!-- Quick Jump Timeline Drawer -->
      <div class="timeline-drawer" id="timelineDrawer" style="display: none;">
        <div class="timeline-header">
          <h3>Jump to Time Window</h3>
          <button class="close-drawer" id="closeDrawer">✕</button>
        </div>
        <div class="timeline-years" id="timelineYears"></div>
      </div>
    `;

    document.body.insertBefore(root, document.body.firstChild);

    // Bind event handlers
    document.getElementById('btn-scroll-top').addEventListener('click', () => {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });

    document.getElementById('btn-scroll-bottom').addEventListener('click', () => {
      window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
    });

    document.getElementById('btn-toggle-order').addEventListener('click', () => {
      applyOrder(!isNewestOnTop);
    });

    const datePill = document.getElementById('datePill');
    const drawer = document.getElementById('timelineDrawer');
    const closeBtn = document.getElementById('closeDrawer');

    datePill.addEventListener('click', () => {
      const isOpen = drawer.style.display !== 'none';
      if (isOpen) {
        drawer.style.display = 'none';
      } else {
        renderTimelineDrawer();
        drawer.style.display = 'block';
      }
    });

    closeBtn.addEventListener('click', () => {
      drawer.style.display = 'none';
    });

    // Close drawer when clicking outside
    document.addEventListener('click', (e) => {
      if (!drawer.contains(e.target) && !datePill.contains(e.target)) {
        drawer.style.display = 'none';
      }
    });

    // Initial date update
    updateScrollDate();
  }

  function handleScroll() {
    const pill = document.getElementById('datePill');
    if (pill) {
      pill.classList.add('scrolling');
      clearTimeout(scrollTimeout);
      scrollTimeout = setTimeout(() => {
        pill.classList.remove('scrolling');
      }, 1200);
    }
    updateScrollDate();
  }

  function updateScrollDate() {
    const textEl = document.getElementById('datePillText');
    if (!textEl) return;

    // Find the message element currently visible near the top of the viewport
    const viewportTop = window.scrollY + 80; // offset below sticky header
    let currentElement = null;

    // Binary search or linear sample
    // Check first element below viewportTop
    for (let i = 0; i < messagesList.length; i++) {
      const el = messagesList[i];
      const rect = el.getBoundingClientRect();
      if (rect.bottom >= 60 && rect.top <= window.innerHeight) {
        currentElement = el;
        break;
      }
    }

    if (currentElement && currentElement.dataset.dateLabel) {
      textEl.textContent = currentElement.dataset.dateLabel;
    } else if (messagesList.length > 0) {
      const target = isNewestOnTop ? messagesList[messagesList.length - 1] : messagesList[0];
      const parsed = parseDateFromElement(target);
      if (parsed) {
        textEl.textContent = parsed.label;
      }
    }
  }

  function renderTimelineDrawer() {
    const container = document.getElementById('timelineYears');
    container.innerHTML = '';

    if (monthMap.size === 0) {
      container.innerHTML = '<p style="padding: 20px; text-align: center; color: gray;">No dates available.</p>';
      return;
    }

    // Group keys by year
    const yearsMap = new Map();
    // Sort keys descending (most recent year first)
    const sortedKeys = Array.from(monthMap.keys()).sort().reverse();

    sortedKeys.forEach((key) => {
      const [year, month] = key.split('-');
      if (!yearsMap.has(year)) {
        yearsMap.set(year, []);
      }
      yearsMap.get(year).push(key);
    });

    yearsMap.forEach((keys, year) => {
      const yearSection = document.createElement('div');
      yearSection.className = 'timeline-year-group';

      const yearTitle = document.createElement('div');
      yearTitle.className = 'timeline-year-title';
      yearTitle.textContent = year;
      yearSection.appendChild(yearTitle);

      const monthsGrid = document.createElement('div');
      monthsGrid.className = 'timeline-months-grid';

      keys.forEach((key) => {
        const monthNum = parseInt(key.split('-')[1], 10);
        const monthName = MONTH_NAMES[monthNum - 1];
        const count = monthCounts.get(key) || 0;

        const btn = document.createElement('button');
        btn.className = 'timeline-month-btn';
        btn.innerHTML = `<span class="month-name">${monthName}</span><span class="month-count">${count}</span>`;

        btn.addEventListener('click', () => {
          jumpToMonth(key);
        });

        monthsGrid.appendChild(btn);
      });

      yearSection.appendChild(monthsGrid);
      container.appendChild(yearSection);
    });
  }

  function jumpToMonth(dateKey) {
    const targetEl = monthMap.get(dateKey);
    const drawer = document.getElementById('timelineDrawer');
    if (drawer) drawer.style.display = 'none';

    if (!targetEl) return;

    // Smooth scroll to target message
    const headerOffset = 70;
    const elementPosition = targetEl.getBoundingClientRect().top;
    const offsetPosition = elementPosition + window.pageYOffset - headerOffset;

    window.scrollTo({
      top: offsetPosition,
      behavior: 'smooth'
    });

    // Highlight message momentarily
    targetEl.classList.add('jump-highlight');
    setTimeout(() => {
      targetEl.classList.remove('jump-highlight');
    }, 2000);
  }

  function handleParentMessage(e) {
    if (!e.data || typeof e.data !== 'object') return;
    if (e.data.action === 'scrollToTop') {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } else if (e.data.action === 'scrollToBottom') {
      window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
    } else if (e.data.action === 'toggleOrder') {
      applyOrder(!isNewestOnTop);
    } else if (e.data.action === 'toggleDrawer') {
      const drawer = document.getElementById('timelineDrawer');
      if (drawer) {
        const isOpen = drawer.style.display !== 'none';
        if (isOpen) {
          drawer.style.display = 'none';
        } else {
          renderTimelineDrawer();
          drawer.style.display = 'block';
        }
      }
    }
  }

  // Run when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
