# Split by tools/split_tests.py; edit this area directly after merge.
"""Tier 5: website."""

from __future__ import annotations
import re
import subprocess
from html.parser import HTMLParser
from pathlib import Path
import pytest
from config import APP_EXE, DESKTOP_DIR, SERVER_DIR, TEST_BLOCK_APP, WEBSITE_DIR
from ._helpers import NODE_EXE, _FooterLinkParser



class TestFooterLinksPointToRealPages:
    """
    A footer link that 404s is worse than no link. The changelog and support
    pages are new, so this guards them and every other relative page link the
    three public pages advertise.
    """

    PAGES = ("index.html", "legal.html", "success.html")
    NEW_PAGES = ("changelog.html", "support.html")

    @classmethod
    def footer_links(cls, name: str) -> list[str]:
        parser = _FooterLinkParser()
        parser.feed((Path(WEBSITE_DIR) / name).read_text(encoding="utf-8"))
        return parser.footer_links

    def test_every_relative_html_link_exists(self):
        for name in self.PAGES:
            for href in self.footer_links(name):
                path = href.split("#", 1)[0]
                if not path.endswith(".html"):
                    continue
                if path.startswith(("http://", "https://", "//", "/")):
                    continue
                assert (Path(WEBSITE_DIR) / path).is_file(), \
                    f"{name} footer links to missing {href}"

    def test_changelog_and_support_are_linked_from_every_footer(self):
        for name in self.PAGES:
            paths = {href.split("#", 1)[0] for href in self.footer_links(name)}
            for page in self.NEW_PAGES:
                assert page in paths, f"{name} footer has no link to {page}"


class TestWebsiteAccessibilityStyles:
    """
    Roadmap 6.7: interactive elements need a visible keyboard focus style, and
    non-essential motion must be disabled for users who ask for reduced motion.
    """

    def test_website_has_focus_and_reduced_motion_styles(self):
        css = (Path(WEBSITE_DIR) / "styles.css").read_text(encoding="utf-8")

        assert ":focus-visible" in css or ":focus" in css, (
            "styles.css must define a keyboard focus style for interactive elements"
        )
        assert "@media (prefers-reduced-motion: reduce)" in css, (
            "styles.css must disable non-essential motion for reduced-motion users"
        )

    @pytest.mark.parametrize("page", [
        "index.html", "legal.html", "success.html", "changelog.html", "support.html",
    ])
    def test_every_public_page_has_one_main_landmark(self, page):
        html = (Path(WEBSITE_DIR) / page).read_text(encoding="utf-8")
        assert html.count("<main>") == 1 and html.count("</main>") == 1, \
            f"{page} needs exactly one <main> landmark for screen-reader navigation"
        assert html.index("</main>") < html.index("<footer>"), \
            f"{page}: the footer must sit outside <main>"


# ============ the success page must always offer key recovery actions

class TestSuccessPageKeyRecovery:
    """
    Roadmap 5.3: the Stripe checkout success page must never lose the license
    key. Once the key resolves, the page must offer Copy, Email, Activate, and
    Download actions so the buyer can always recover it.
    """

    def test_success_page_offers_key_recovery_actions(self):
        source = (Path(WEBSITE_DIR) / "success.html").read_text(encoding="utf-8")
        assert 'id="copy-key"' in source, "the Copy license key button is missing"
        assert 'id="email-key"' in source, "the Email me this key button is missing"
        assert 'id="activate-link"' in source, "the Activate in Basalt button is missing"
        assert 'id="download-link"' in source, "the Download Basalt button is missing"
        assert "resend-license" not in source or "checkout.js" in source, \
            "the email handler must live in checkout.js, not inline in the HTML"

    def test_the_email_button_is_only_offered_when_the_server_can_send(self):
        """
        /resend-license answers 503 when no mail provider is configured, so
        the button would fail every time on such a server. get-license reports
        emailConfigured; the page hides the button — and stops saying "have it
        emailed to you" — when that is false or the buyer's address is unknown.
        """
        js = (Path(WEBSITE_DIR) / "checkout.js").read_text(encoding="utf-8")
        assert "result.emailConfigured !== false" in js
        assert "emailKeyBtn.style.display = 'none'" in js
        assert "You can copy, email, or activate the key below." not in js

    def test_checkout_js_has_no_byte_order_mark(self):
        # A PowerShell edit once prepended U+FEFF; browsers tolerate it but
        # every later diff of the file shows a phantom first-line change.
        raw = (Path(WEBSITE_DIR) / "checkout.js").read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), "checkout.js starts with a UTF-8 BOM"


# ============ the download guide explains what happens next (roadmap 6.3)

class TestDownloadGuidePanel:
    """
    Clicking Download shows a short "What happens next" panel: the SmartScreen
    step (until the build is signed), running the installer, and the first-run
    welcome. The panel's own Download button must still reach the installer.
    """

    INSTALLER_URL = (
        "https://github.com/seventycookies6-design/flowshield/releases/latest/"
        "download/FlowShield-win-Setup.exe"
    )

    def test_download_guide_panel_mentions_setup_steps(self):
        site = (Path(WEBSITE_DIR) / "index.html").read_text(encoding="utf-8")
        assert 'id="download-panel"' in site, "the download guide panel is missing"
        panel = site.split('id="download-panel"', 1)[1].split("</dialog>", 1)[0]
        lower = panel.lower()
        for phrase in ("smartscreen", "installer", "first run"):
            assert phrase in lower, f"the download guide must mention {phrase!r}"
        assert self.INSTALLER_URL in panel, (
            "the panel's Download button must point at the installer URL"
        )

    def test_the_first_run_step_describes_the_real_welcome(self):
        # The welcome (F18) has three steps — apps, strictness, first sprint —
        # and only starts a sprint if the user presses Start. The draft said it
        # "asks for your blocklist and default sprint, then starts the first
        # sprint", which skipped a step and promised an automatic start.
        site = (Path(WEBSITE_DIR) / "index.html").read_text(encoding="utf-8")
        panel = site.split('id="download-panel"', 1)[1].split("</dialog>", 1)[0]
        vm = (Path(DESKTOP_DIR) / "ViewModels" / "FirstRunViewModel.cs").read_text(encoding="utf-8")
        assert 'StepText => $"Step {Step} of 3"' in vm
        assert "three-step welcome" in panel
        assert "then starts the first sprint" not in panel


# ============ phone visitors get a menu and a copyable download link (roadmap 6.4)

class TestProductCaptures:
    """
    F27: the site shows the real app. DESIGN_SYSTEM.md 10 sets the rules —
    real product only, a surface frame at radius 14 with a soft shadow, never a
    fake device frame — and 11 adds that the hero must render before any media.

    These check the markup and the asset budget. Whether the screenshots make
    the product look good is a human's call and always will be.
    """

    MEDIA = Path(WEBSITE_DIR) / "media"

    def _section(self):
        site = (Path(WEBSITE_DIR) / "index.html").read_text(encoding="utf-8")
        assert 'id="see-it"' in site, "the captures section is missing"
        return site.split('id="see-it"', 1)[1].split("</section>", 1)[0]

    def test_every_capture_referenced_exists(self):
        import re
        for src in re.findall(r'src="(media/[^"]+)"', self._section()):
            assert (Path(WEBSITE_DIR) / src).exists(), f"{src} is referenced but missing"

    def test_every_image_has_real_alt_text(self):
        import re
        images = re.findall(r"<img[^>]*>", self._section(), re.S)
        assert images, "the section has no screenshots"
        for tag in images:
            alt = re.search(r'alt="([^"]*)"', tag, re.S)
            assert alt, f"an image has no alt attribute: {tag[:80]}"
            assert len(" ".join(alt.group(1).split())) > 25, (
                "alt text has to describe the screen, not just name it"
            )

    def test_images_are_lazy_and_reserve_their_space(self):
        import re
        for tag in re.findall(r"<img[^>]*>", self._section(), re.S):
            assert 'loading="lazy"' in tag, "captures must not block the page"
            assert "width=" in tag and "height=" in tag, (
                "give every image its size so the page does not jump"
            )

    def test_no_fake_device_frames(self):
        """
        Checks the markup, not the prose: the copy is allowed to say "not a
        mock-up", which is rather the point of the section.
        """
        import re
        section = self._section()
        attributes = " ".join(
            re.findall(r'(?:class|src|id)="([^"]*)"', section)
        ).lower()
        for banned in ("laptop", "macbook", "iphone", "device-frame", "mockup", "mock-up"):
            assert banned not in attributes, f"DESIGN_SYSTEM 10 forbids a {banned} frame"

    def test_screenshot_frame_uses_theme_tokens(self):
        """Screenshot framing stays theme-aware without fixing its CSS recipe."""
        site = (Path(WEBSITE_DIR) / "index.html").read_text(encoding="utf-8")
        capture = re.search(
            r'<figure\b[^>]*class="([^"]+)"[^>]*>.*?<img\b[^>]*src="media/',
            site, re.S)
        assert capture, "the page needs a figure around a real product capture"
        frame_classes = set(capture.group(1).split())

        css = (Path(WEBSITE_DIR) / "styles.css").read_text(encoding="utf-8")
        rules = re.findall(r"([^{}]+)\{([^{}]*)\}", css)
        frame_rules = [
            declarations for selectors, declarations in rules
            if any(re.search(r"\." + re.escape(name) + r"(?![\w-])", selectors)
                   for name in frame_classes)
        ]
        assert any("var(--" in declarations for declarations in frame_rules), (
            "product captures must use the current theme tokens for their frame")

    def test_the_captures_stay_within_a_sensible_budget(self):
        """
        DESIGN_SYSTEM 11: the hero renders before any media. Lazy loading does
        the work, but a page of multi-megabyte PNGs is still rude on a phone.
        """
        if not self.MEDIA.exists():
            pytest.skip("no media directory yet")
        total = 0
        for asset in self.MEDIA.glob("*.png"):
            size = asset.stat().st_size
            assert size < 900_000, f"{asset.name} is {size / 1000:.0f} kB; compress it"
            total += size
        assert total < 3_000_000, f"the captures total {total / 1000:.0f} kB"

    def test_the_recording_is_silent_looping_and_inline(self):
        """DESIGN_SYSTEM.md 10: muted, looping, a poster, playsinline."""
        section = self._section()
        video = section.split("<video", 1)[1].split(">", 1)[0]
        for attribute in ("muted", "loop", "playsinline", "poster="):
            assert attribute in video, f"the recording must set {attribute}"
        assert "controls" not in video, "a looping silent demo needs no controls by default"
        assert "<audio" not in section
        assert "autoplay" not in video, (
            "autoplay belongs to the reduced-motion script, not the markup"
        )

    def test_the_recording_honours_reduced_motion(self):
        """
        DESIGN_SYSTEM.md 8: with reduced motion on, the video shows its poster
        frame instead of playing. There is no HTML or CSS way to make autoplay
        conditional, so a script decides — and this checks the script exists and
        keys off the right query.
        """
        site = (Path(WEBSITE_DIR) / "index.html").read_text(encoding="utf-8")
        assert "prefers-reduced-motion: reduce" in site
        script = site.split("prefers-reduced-motion: reduce", 1)[1][:600]
        assert ".pause()" in script, "reduced motion has to stop the video"

    def test_the_recording_is_described_for_people_who_cannot_see_it(self):
        section = self._section()
        assert "aria-describedby" in section
        described = section.split('id="shield-demo-description"', 1)[1].split("</p>", 1)[0]
        assert len(" ".join(described.split())) > 80, (
            "a silent demo needs a description that says what happens in it"
        )

    def test_the_recording_stays_inside_the_size_budget(self):
        """DESIGN_SYSTEM.md 10: about 2 MB on desktop, 1 MB on mobile."""
        if not self.MEDIA.exists():
            pytest.skip("no media directory yet")
        for clip in list(self.MEDIA.glob("*.webm")) + list(self.MEDIA.glob("*.mp4")):
            size = clip.stat().st_size
            assert size < 2_000_000, f"{clip.name} is {size / 1000:.0f} kB"

    def test_the_recording_does_not_load_before_the_page(self):
        video = self._section().split("<video", 1)[1].split(">", 1)[0]
        assert 'preload="none"' in video, (
            "DESIGN_SYSTEM.md 11: the hero renders before any media loads"
        )

    def test_hero_cta_warning_and_day_content_remain_available(self):
        """
        #147 §4 (issue #173, "B2") deliberately reverses part of #139: the
        hero itself now shows the real Today capture, full width, directly
        below the copy — it no longer sits beside a decorative day-mock, and
        the day timeline is promoted to its own `#day` section right after
        the hero instead. What #139 actually protected — that the hero's
        text and primary button render before any product media, and that
        the below-the-fold proof section never displaces the hero — still
        holds and is checked more precisely here, not weakened.
        """
        site = (Path(WEBSITE_DIR) / "index.html").read_text(encoding="utf-8")
        hero_open = site.index('<section class="hero"')
        hero = site[hero_open:site.index("</section>", hero_open)]
        assert "data-download-guide" in hero, "the hero must keep its download action"
        assert "data-smartscreen-note" in hero, "the unsigned-build caveat must stay available"
        assert "media/today.png" in hero, "the hero must show a real product capture"
        assert hero.index("data-download-guide") < hero.index("media/today.png"), (
            "the call to action must remain available before the product capture")
        assert hero.index("data-smartscreen-note") < hero.index("media/today.png"), (
            "the SmartScreen caveat must remain available before the product capture")

        day = site.index('<section id="day"')
        day_section = site[day:site.index("</section>", day)]
        assert 'aria-hidden="true"' not in day_section.split(">", 1)[0], (
            "the day section itself must not be hidden from assistive tech"
        )
        assert re.search(r"<h[1-6][ >]", day_section), (
            "the day content needs an accessible heading")



class TestDesignReviewFixesB4:
    """
    #183: an external review of the site stack found these, and each was
    re-measured in a browser before the fix. Every test below fails on the
    markup and CSS as #178 left them.
    """

    SITE = Path(WEBSITE_DIR) / "index.html"
    CSS = Path(WEBSITE_DIR) / "styles.css"

    def _css(self) -> str:
        return self.CSS.read_text(encoding="utf-8")

    def _rule(self, selector: str) -> str:
        # Anchored to the start of a line, so ".shot-grid" can't match the
        # tail of a compound selector such as ".shot-demo + .shot-grid".
        css = self._css()
        match = re.search(r"^" + re.escape(selector) + r" \{", css, re.M)
        assert match, f"no top-level rule for {selector}"
        return css[match.start():css.index("}", match.start())]

    def test_the_mobile_menu_closes_when_a_destination_is_chosen(self):
        """At 390px, tapping a nav link scrolled to the section but left the
        open menu covering it."""
        site = self.SITE.read_text(encoding="utf-8")
        script = site[site.index("[data-menu-toggle]');"):]
        assert "#primary-nav a" in script and "setMenu(false)" in script, (
            "a nav link must close the menu when it is chosen")
        assert "'Escape'" in script, "Escape must close the open menu"
        assert "scroll-padding-top" in self._css(), (
            "in-page links must land below the sticky header, not under it")


    def test_gallery_columns_cannot_outgrow_a_narrow_phone(self):
        """At 360px the grid was narrower than a 20rem column, so cards ran past
        the right gutter."""
        rule = self._rule(".shot-grid")
        assert "minmax(min(100%, 20rem), 1fr)" in rule, (
            "the column minimum must be capped at the grid's own width")

    def test_no_decorative_status_or_accent_colour(self):
        """§2: teal marks state, selection or progress, and status colours are
        for status only. Static icons, a quote rule and fake window dots were
        using them as decoration."""
        css = self._css()
        assert ".mock-bar i:first-child" not in css, "no red/amber/green window dots"
        site = self.SITE.read_text(encoding="utf-8")
        assert '<div class="mock-bar"><i>' not in site, "the window-dot markup is gone too"
        assert "var(--color-primary)" not in self._rule(".behaviors li svg")
        assert "color: var(--color-primary)" not in css[css.index(".feature-icon svg"):][:120]
        assert "solid var(--color-primary)" not in self._rule(".hero .example")

    def test_pricing_offers_phones_the_same_download_flow_as_the_hero(self):
        """On a phone the hero copied the download link, while pricing still
        offered the Windows installer."""
        site = self.SITE.read_text(encoding="utf-8")
        pricing = site[site.index('<section id="pricing"'):]
        pricing = pricing[:pricing.index("</section>")]
        assert "data-download-direct" in pricing, (
            "pricing's installer link must hide on phones like the hero's")
        assert "data-download-copy" in pricing, "pricing needs the phone copy button"
        assert "data-copy-confirm" in pricing, "and a confirmation beside it"
        assert "querySelectorAll('[data-download-copy]')" in site, (
            "every copy button must be wired, not just the first one")



class TestLandingPageLengthB5:
    """
    #185: the external review found the page repeating itself before the
    decision point. Pricing started about 7,900px down on desktop and
    10,200px on a phone. The day was explained three times (the timeline,
    #how, and a strip in #shields), momentum four times, and the Today
    capture shown twice. These guard the cut against creeping back.
    """

    SITE = Path(WEBSITE_DIR) / "index.html"

    def _site(self) -> str:
        return self.SITE.read_text(encoding="utf-8")


    def test_the_day_is_explained_once(self):
        site = self._site()
        day = site[site.index('<section id="day"'):]
        day = day[:day.index("</section>")]
        assert 'class="timeline"' in day and 'class="story-list' in day, (
            "#day carries both the timeline and the three steps")
        assert 'class="day-strip"' not in site, (
            "the shields section must not repeat the day as a strip")



    def test_benefits_do_not_restate_other_sections(self):
        site = self._site()
        features = site[site.index('<section id="features"'):site.index('<section id="pricing"')]
        for repeat in ("Escalating shield levels", "Momentum first", "Why it sticks"):
            assert repeat not in features, f"{repeat!r} restates another section"
        assert features.count('class="surface feature"') == 3


class TestSiteToneB6:
    """
    #187: "Pick how much you trust yourself today" and "when you do not trust
    yourself" framed the reader as untrustworthy. Miles chose to rewrite both
    and to keep "The 1 a.m. version of you doesn't get a vote", which sides
    with the reader against an impulse they chose to guard against
    (DESIGN_SYSTEM.md §9: kind, never guilty).
    """

    def _site(self) -> str:
        return " ".join((Path(WEBSITE_DIR) / "index.html").read_text(encoding="utf-8").split())

    def test_the_site_does_not_call_the_reader_untrustworthy(self):
        site = self._site().lower()
        for phrase in ("trust yourself", "not trust yourself"):
            assert phrase not in site, f"{phrase!r} frames the reader as untrustworthy"



class TestPhoneVisitorMarkup:
    """
    Roadmap 6.4: on small screens the nav collapses behind a hamburger and the
    hero's direct installer link is replaced by a "Get the download link" button
    that copies the URL, falling back to a mailto: link when the clipboard is
    unavailable. The desktop direct link must stay intact.
    """

    def test_phone_visitor_markup(self):
        site = (Path(WEBSITE_DIR) / "index.html").read_text(encoding="utf-8")
        css = (Path(WEBSITE_DIR) / "styles.css").read_text(encoding="utf-8")

        # A hamburger/menu control exists and is wired to the nav links.
        assert "data-menu-toggle" in site, "no hamburger/menu control on the page"
        assert 'aria-controls="primary-nav"' in site, "menu button is not wired to the nav"
        assert 'id="primary-nav"' in site, "the nav links have no id to toggle"

        # The direct installer link is still present somewhere in the page.
        assert "FlowShield-win-Setup.exe" in site, "the direct installer link was removed"

        # A copy button with a mailto fallback exists for mobile.
        assert "data-download-copy" in site, "no mobile copy-download button"
        assert "data-download-direct" in site, "no direct download link to copy from"
        assert "mailto:" in site, "no mailto fallback for phones without a clipboard"
        assert "navigator.clipboard" in site, "no clipboard copy path"

        # CSS hides the direct button on mobile and the copy button on desktop.
        assert "[data-download-copy]" in css, "copy button is not hidden on desktop"
        assert "data-download-direct" in css, "direct button is not hidden on mobile"

        # #193: the swap is deliberate, so the phone says why. Without it the
        # missing installer button reads as a broken page. It is shown by the
        # same breakpoint that hides the direct link, so the two cannot drift.
        assert 'class="phone-only"' in site, "phones get no reason for the copy button"
        assert ".hero-note .phone-only { display: inline; }" in css, (
            "the phone explanation must appear at the breakpoint that hides the installer link")


# ================================ the conversion pass from evidence (#193)

class TestSiteConversionPass:
    """
    #193. Three things the landing page owed a visitor, each backed by a
    source rather than taste:

    * The SmartScreen warning explained **before** the download click, not
      only inside the panel that opens after it. Microsoft's guidance for an
      unsigned build is to tell people in advance that they will see the
      prompt, and `SELLING.md` already calls it the biggest install drop-off.
    * The refund reachable from the decision point. It existed only in
      `legal.html` and a footer link.
    * Calls to action that name what the click does (NN/g, *"Get Started"
      Stops Users*, 2017: "a link is a promise").

    Every claim added here is one the shipped product can back: a refund
    policy that exists, no account, no telemetry. No testimonials, no user
    counts, no invented numbers.
    """

    INDEX = Path(WEBSITE_DIR) / "index.html"

    def _site(self) -> str:
        return self.INDEX.read_text(encoding="utf-8")

    def _copy(self) -> str:
        """The page with its HTML comments removed — what a visitor reads.

        The comments in this file quote the old wording and name the things
        being guarded against, so scanning the raw source for banned copy
        matches the explanation of the ban.
        """
        return re.sub(r"<!--.*?-->", "", self._site(), flags=re.S)

    def _hero(self) -> str:
        site = self._site()
        start = site.index('<section class="hero"')
        return site[start:site.index("</section>", start)]

    def test_unsigned_build_warning_precedes_download(self):
        """Unsigned builds explain SmartScreen in the download flow before the installer link."""
        site = self._site()
        dialog_start = site.index("<dialog")
        dialog = site[dialog_start:site.index("</dialog>", dialog_start)]
        lower = dialog.lower()
        warning = lower.find("windows protected your pc")
        download = lower.find("href=", warning)
        assert warning >= 0, "the download flow must explain the Windows warning"
        assert "code-signed" in lower[:download], "explain why the unsigned build warns"
        assert "run anyway" in lower[:download], "explain how to continue past the warning"
        assert download > warning, "explain SmartScreen before the installer download"

    def test_the_smartscreen_note_goes_when_the_build_is_signed(self):
        """
        F25 buys a certificate and adds signing to `tools/build_release.ps1`.
        The day that lands, this note becomes a lie; fail then, loudly.
        """
        script = (Path(DESKTOP_DIR).parent / "tools" / "build_release.ps1").read_text(
            encoding="utf-8-sig")
        assert "NOT CODE SIGNED" in script, (
            "build_release.ps1 no longer warns that the build is unsigned — if F25 "
            "landed, delete the hero SmartScreen note, the FAQ paragraph about it "
            "and this test")

    def test_refund_terms_are_in_the_purchase_flow(self):
        site = self._site()
        pricing = site.split('<section id="pricing">', 1)[1].split("</section>", 1)[0]
        assert "14-day refund" in pricing or "14 days" in pricing
        assert 'href="legal.html#refunds"' in pricing, (
            "the purchase flow must link to the refund policy")
        # And the promise has to match the policy it links to.
        legal = (Path(WEBSITE_DIR) / "legal.html").read_text(encoding="utf-8")
        assert "within 14 days" in legal, (
            "the refund window on the landing page no longer matches legal.html")

    def test_faq_explains_refunds_and_links_to_terms(self):
        faq = self._site().split('id="faq"', 1)[1].split("</section>", 1)[0]
        refund_entries = re.findall(r"<details\b.*?</details>", faq, re.S)
        assert any("14 days" in entry and "legal.html#refunds" in entry
                   for entry in refund_entries), (
            "a FAQ answer must explain the refund window and link to its legal terms")

    def test_the_download_buttons_say_what_the_click_does(self):
        """
        NN/g (Harley & Flaherty, 20 Aug 2017): state precisely what users
        should expect. "Start free trial" never said an installer downloads.
        """
        copy = self._copy()
        assert "Start free trial" not in copy and "Start the free trial" not in copy, (
            "a download button must name the download")
        # Both offers — the hero and the pricing card — carry the same label.
        assert copy.count("Download for Windows") == 2

    def test_no_invented_trust_signals(self):
        """
        Zero customers means zero testimonials. The only honest trust signals
        are checkable facts, so guard against the usual substitutes.
        """
        lower = self._copy().lower()
        for banned in ("testimonial", "customers love", "trusted by", "5 stars",
                       "rated 5", "join thousands", "users worldwide", "money-back guarantee!"):
            assert banned not in lower, f"{banned!r} is not something this product can back"

    def test_every_relative_page_link_on_every_public_page_exists(self):
        """
        `TestFooterLinksPointToRealPages` only walks footers, so the FAQ's
        link to a `privacy.html` that has never existed survived for months.
        This walks every relative link on every public page.
        """
        pages = ("index.html", "legal.html", "success.html",
                 "changelog.html", "support.html")
        for name in pages:
            html = (Path(WEBSITE_DIR) / name).read_text(encoding="utf-8")
            for href in re.findall(r'href="([^"]+)"', html):
                if href.startswith(("http://", "https://", "//", "/", "#",
                                    "mailto:", "data:", "flowshield:")):
                    continue
                path, _, fragment = href.partition("#")
                if not path.endswith(".html"):
                    continue
                target = Path(WEBSITE_DIR) / path
                assert target.is_file(), f"{name} links to missing {href}"
                if fragment:
                    assert f'id="{fragment}"' in target.read_text(encoding="utf-8"), \
                        f"{name} links to {href}, but {path} has no id={fragment!r}"

class TestTheSiteStaysOfflineForTheBeta:
    """
    The site is offline for the internal beta (#165): GitHub Pages' terms
    forbid selling from it, so it moves host before launch (#166). The
    publish script refuses without -BetaIsOver so that an agent following an
    older instruction cannot quietly put it back up.
    """

    SCRIPT = Path(__file__).resolve().parents[3] / "tools" / "publish_site.ps1"

    def test_publishing_needs_an_explicit_switch(self):
        script = self.SCRIPT.read_text(encoding="utf-8")
        assert "param([switch]$BetaIsOver)" in script
        guard = script.split("if (-not $BetaIsOver)", 1)
        assert len(guard) == 2, "the refusal is gone"
        refusal = guard[1].split("}", 1)[0]
        assert "exit 1" in refusal, "refusing must stop the script, not just warn"

    def test_the_refusal_comes_before_anything_is_pushed(self):
        script = self.SCRIPT.read_text(encoding="utf-8")
        guard = script.index("if (-not $BetaIsOver)")
        # Everything before the guard is the help block and the param line:
        # no git call, no push, nothing that reaches gh-pages.
        before = script[:guard].split("#>", 1)[1]
        for command in ("git ", "Invoke-Git", "push", "Set-Location"):
            assert command not in before, (
                f"{command!r} runs before the beta guard, so it happens even when publishing is refused"
            )
        assert script.index("Invoke-Git", guard) > guard


# =================== the site self-hosts Inter, no third-party font host (B1)

class TestSiteFontsAreSelfHosted:
    """
    DESIGN_SYSTEM.md #147/#149: Inter replaces Syne + Source Sans 3, self-
    hosted under Website/fonts/ so the site never contacts Google Fonts.
    Written to fail against the pre-B1 site (Google Fonts <link>s in every
    page's <head>, no Website/fonts/ directory) before the fix landed.
    """

    FONTS_DIR = Path(WEBSITE_DIR) / "fonts"
    CSS = Path(WEBSITE_DIR) / "styles.css"
    PAGES = ["index.html", "support.html", "changelog.html", "legal.html", "success.html"]

    @pytest.mark.parametrize("page", PAGES)
    def test_no_page_references_a_third_party_font_host(self, page):
        html = (Path(WEBSITE_DIR) / page).read_text(encoding="utf-8")
        assert "fonts.googleapis.com" not in html, f"{page} still links Google Fonts"
        assert "fonts.gstatic.com" not in html, f"{page} still preconnects to Google Fonts"

    def test_every_font_face_src_file_exists_on_disk(self):
        css = self.CSS.read_text(encoding="utf-8")
        faces = re.findall(r"@font-face\s*{[^}]*}", css)
        assert faces, "styles.css has no @font-face rule — Inter isn't self-hosted"
        found_local_src = False
        checked_any_url = 0
        for face in faces:
            for url_match in re.finditer(r'url\(["\']?([^"\')]+)["\']?\)', face):
                checked_any_url += 1
                src_path = (Path(WEBSITE_DIR) / url_match.group(1)).resolve()
                assert src_path.is_file(), f"@font-face src file is missing: {url_match.group(1)}"
            if "local(" in face:
                found_local_src = True
        assert checked_any_url, "no @font-face rule has a url() src — nothing is actually self-hosted"
        assert found_local_src, "the size-adjusted local() fallback face is missing"

    def test_ofl_license_is_present(self):
        license_file = self.FONTS_DIR / "OFL.txt"
        assert license_file.is_file(), "Website/fonts/OFL.txt is missing"
        text = license_file.read_text(encoding="utf-8")
        assert "SIL OPEN FONT LICENSE" in text.upper()

    def test_fallback_face_is_size_adjusted_to_avoid_reflow(self):
        """
        §11: the hero must render text before any image loads, which only
        holds if the fallback-to-Inter swap doesn't visibly reflow it.
        """
        css = self.CSS.read_text(encoding="utf-8")
        fallback = css.split('font-family: "Inter Fallback";', 1)
        assert len(fallback) == 2, "the size-adjusted local fallback face is missing"
        block = fallback[1].split("}", 1)[0]
        for descriptor in ("size-adjust", "ascent-override", "descent-override"):
            assert descriptor in block, f"the Inter Fallback face is missing {descriptor}"

    def test_no_page_sets_swap_display_without_self_hosting(self):
        # font-display: swap only helps if the font is actually local — make
        # sure the primary Inter face uses it.
        css = self.CSS.read_text(encoding="utf-8")
        primary = css.split('font-family: "Inter";', 1)[1].split("}", 1)[0]
        assert "font-display: swap" in primary


# ==================================================== B3 — site system pass

class TestSiteSystemPassB3:
    """
    DESIGN_SYSTEM.md §5-§7 / UI-SPEC.md B3: the full §7 button set at 44px,
    the §6 shield glyph symbol set (echoing the app's A4
    DesktopApp/Styles/ShieldGlyphs.xaml), the missing 6px chip radius step,
    section rhythm on the 4-scale, and Lucide icons in place of the FAQ's
    Unicode +/- markers. Written to fail against the pre-B3 site (plain-text
    "Shield II" labels, no .btn-quiet/.btn-danger, no --radius-chip, 48/64px
    section padding, a "+"/mojibake "-" FAQ marker) before the fix landed.
    """

    CSS = Path(WEBSITE_DIR) / "styles.css"
    INDEX = Path(WEBSITE_DIR) / "index.html"
    def test_site_buttons_meet_the_touch_target_minimum(self):
        """Every button style keeps the 44px minimum touch target."""
        css = self.CSS.read_text(encoding="utf-8")
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        rules = re.findall(r"([^{}]+)\{([^{}]*)\}", css)
        for variant in (".btn-primary", ".btn-ghost", ".btn-quiet", ".btn-danger"):
            effective = {}
            for selectors, body in rules:
                if not {".btn", variant}.intersection(
                        part.strip() for part in selectors.split(",")):
                    continue
                for prop, value in re.findall(
                        r"(min-height|height)\s*:\s*(\d+(?:\.\d+)?)px", body):
                    effective[prop] = float(value)
            assert effective.get("min-height", 0) >= 44 or effective.get("height", 0) >= 44, (
                f"{variant} must keep a height or min-height of at least 44px")


    def test_shield_levels_are_distinct_and_legible(self):
        """Shield levels must remain distinguishable with theme-aware contrast."""
        html = self.INDEX.read_text(encoding="utf-8")
        section = html.split('id="shields"', 1)[1].split('id="see-it"', 1)[0]
        symbols = re.findall(r'<symbol\b[^>]*id="([^"]+)"[^>]*>(.*?)</symbol>', html, re.S)
        used = {target for target in re.findall(r'<use\b[^>]*href="#([^"]+)"', section)}
        shipped = [(key, body) for key, body in symbols if key in used]
        assert shipped, "the shield levels need visible glyphs"
        color_sets = [frozenset(re.findall(r"var\((--color-[\w-]+)\)", body))
                      for _, body in shipped]
        assert len(set(color_sets)) == len(color_sets), (
            "each shield level must use a distinguishable theme contrast treatment")
        for key, body in shipped:
            assert re.search(r"(?:fill|stroke)=\"var\(--color-[\w-]+\)\"", body), (
                f"{key} must use accessible theme color tokens")
        assert not re.search(r"(?:fill|stroke)=\"#[0-9A-Fa-f]{3,8}\"", "".join(
            body for _, body in shipped)), "shield glyph colors must follow the theme"




    def test_faq_disclosures_have_clear_indicators(self):
        html = self.INDEX.read_text(encoding="utf-8")
        faq = html.split('id="faq"', 1)[1].split("</section>", 1)[0]
        entries = re.findall(r"<details\b.*?</details>", faq, re.S)
        assert entries, "the FAQ needs native disclosure controls"
        css = self.CSS.read_text(encoding="utf-8")
        native_marker_hidden = re.search(
            r"summary[^{}]*(?:::\s*marker|::-webkit-details-marker)[^{}]*\{[^}]*"
            r"(?:display\s*:\s*none|content\s*:\s*none)", css, re.S)
        for entry in entries:
            summary = re.search(r"<summary\b[^>]*>(.*?)</summary>", entry, re.S)
            assert summary, "each FAQ disclosure needs a visible summary and its native indicator"
            label = re.sub(r"<[^>]+>", " ", summary.group(1)).strip()
            assert label, "each FAQ disclosure needs an understandable label"
            if native_marker_hidden:
                assert re.search(r"<(?:svg|img)\b", summary.group(1)), (
                    "a custom indicator must remain when the browser marker is hidden")

    def test_every_feature_card_has_an_icon(self):
        html = self.INDEX.read_text(encoding="utf-8")
        features = html.split('id="features"', 1)[1].split('id="pricing"', 1)[0]
        from html.parser import HTMLParser

        class Node:
            def __init__(self, tag, attrs, parent=None):
                self.tag = tag
                self.attrs = dict(attrs)
                self.parent = parent
                self.children = []

        class Tree(HTMLParser):
            VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
                    "link", "meta", "param", "source", "track", "wbr"}

            def __init__(self):
                super().__init__()
                self.root = Node("root", ())
                self.stack = [self.root]

            def handle_starttag(self, tag, attrs):
                node = Node(tag, attrs, self.stack[-1])
                self.stack[-1].children.append(node)
                if tag not in self.VOID:
                    self.stack.append(node)

            def handle_endtag(self, tag):
                for index in range(len(self.stack) - 1, 0, -1):
                    if self.stack[index].tag == tag:
                        del self.stack[index:]
                        break

        tree = Tree()
        tree.feed(features)
        section = tree.root.children[0]

        def descendants(node):
            for child in node.children:
                yield child
                yield from descendants(child)

        headings = [node for node in descendants(section) if node.tag in ("h3", "h4")]
        assert headings, "the feature section needs customer-facing features"
        for heading in headings:
            container = heading.parent
            has_icon = False
            while container is not None and container is not section:
                nested = list(descendants(container))
                if sum(node.tag in ("h3", "h4") for node in nested) > 1:
                    break
                if any(node.tag in ("svg", "img") for node in nested):
                    has_icon = True
                    break
                container = container.parent
            assert has_icon, "every feature card needs an icon"

    def test_no_legacy_colour_aliases_reintroduced_by_this_pass(self):
        # TestNoLegacyColourAliases already covers the app and the general
        # site case; this just re-confirms the exact files B3 touched.
        css = self.CSS.read_text(encoding="utf-8")
        html = self.INDEX.read_text(encoding="utf-8")
        for name in ("--violet", "--cyan", "--grad"):
            assert f"{name}:" not in css
            assert f"var({name})" not in html


# ============ the ?server= override must not redirect a customer's email (#285)

class TestSiteServerOverrideIsLocalOnly:
    """
    `Website/checkout.js` used to take the licence server from `?server=` on
    any host, so a shared link such as `support.html?server=https://attacker`
    made the Lost-your-key form post the typed email to that server. The
    override is for tests: it is honoured only on a localhost copy and only
    toward a loopback address. Runs the real script in node with a stub DOM.
    """

    HARNESS = r"""
    const fs = require('fs'), vm = require('vm');
    const [host, search, src] = process.argv.slice(1);
    const sandbox = {
      window: {
        location: { hostname: host, search: search },
        FLOWSHIELD_CONFIG: { licenseServerUrl: 'https://licence.example.test' },
      },
      document: { getElementById: () => null, querySelector: () => null,
                  querySelectorAll: () => [], addEventListener: () => {} },
      URLSearchParams, URL, console, setTimeout, fetch: () => Promise.reject(new Error('x')),
    };
    vm.createContext(sandbox);
    vm.runInContext(fs.readFileSync(src, 'utf8'), sandbox);
    process.stdout.write(sandbox.window.FlowShield.SERVER);
    """

    def _server(self, host: str, search: str) -> str:
        result = subprocess.run(
            [NODE_EXE, "-e", self.HARNESS, host, search,
             str(Path(WEBSITE_DIR) / "checkout.js")],
            capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
        return result.stdout

    def test_production_host_ignores_the_override(self):
        got = self._server("basalt.example", "?server=https://attacker.example")
        assert got == "https://licence.example.test"

    def test_localhost_only_accepts_a_loopback_target(self):
        assert self._server("localhost", "?server=http://localhost:3999") == "http://localhost:3999"
        assert self._server("localhost", "?server=https://attacker.example") \
            == "https://licence.example.test"

    def test_non_urls_are_ignored(self):
        assert self._server("localhost", "?server=javascript:alert(1)") \
            == "https://licence.example.test"
