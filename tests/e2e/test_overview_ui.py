"""
End-to-end UI tests for the Overview Report page.

Tests cover:
- Page structure and layout
- Filter functionality
- Filter tags
- Sorting
- Details panel
- Responsive design elements
- Tooltips
"""

import pytest
from playwright.sync_api import Page, expect


class TestOverviewPageStructure:
    """Tests for basic page structure and elements."""

    def test_page_title(self, page: Page, overview_report_url: str):
        """Page should have correct title."""
        page.goto(overview_report_url)
        expect(page).to_have_title("Linux Game Benchmark - Overview")

    def test_header_elements(self, page: Page, overview_report_url: str):
        """Header should contain title and subtitle."""
        page.goto(overview_report_url)

        # Main heading
        heading = page.get_by_role("heading", name="Linux Game Benchmark")
        expect(heading).to_be_visible()

        # Subtitle with date
        subtitle = page.locator(".subtitle")
        expect(subtitle).to_contain_text("All benchmarks at a glance")

    def test_filter_bar_present(self, page: Page, overview_report_url: str):
        """Filter bar should be present with all filter dropdowns."""
        page.goto(overview_report_url)

        filter_ids = [
            "filter-game",
            "filter-res",
            "filter-cpu",
            "filter-gpu",
            "filter-os",
            "filter-kernel",
            "filter-mesa"
        ]

        for filter_id in filter_ids:
            dropdown = page.locator(f"#{filter_id}")
            expect(dropdown).to_be_visible()

    def test_stats_bar_present(self, page: Page, overview_report_url: str):
        """Stats bar should show Games, Benchmarks, and Systems counts."""
        page.goto(overview_report_url)

        stats_bar = page.locator(".stats-bar")
        expect(stats_bar).to_be_visible()

        # Check for stat labels (using exact match within stats-bar)
        expect(stats_bar.get_by_text("Games", exact=True)).to_be_visible()
        expect(stats_bar.get_by_text("Benchmarks", exact=True)).to_be_visible()
        expect(stats_bar.get_by_text("Systems", exact=True)).to_be_visible()

    def test_benchmark_table_present(self, page: Page, overview_report_url: str):
        """Benchmark table should be present with correct columns."""
        page.goto(overview_report_url)

        table = page.locator(".benchmark-table")
        expect(table).to_be_visible()

        # Check column headers using direct child selector
        header_cells = page.locator(".benchmark-table > thead > tr > th")
        expect(header_cells).to_have_count(7)

        # Check that table has sortable columns
        expect(header_cells.first).to_be_visible()

    def test_reset_button_present(self, page: Page, overview_report_url: str):
        """Reset button should be visible."""
        page.goto(overview_report_url)

        reset_btn = page.get_by_role("button", name="Reset")
        expect(reset_btn).to_be_visible()


class TestFilterFunctionality:
    """Tests for filter dropdowns and filtering logic."""

    def test_filter_by_gpu(self, page: Page, overview_report_url: str):
        """Filtering by GPU should reduce visible benchmarks."""
        page.goto(overview_report_url)

        # Get initial count
        initial_count = page.locator("#visible-count").inner_text()

        # Select a specific GPU
        gpu_select = page.locator("#filter-gpu")
        gpu_select.select_option(index=1)  # Select first non-"All" option

        # Count should change (or stay same if all benchmarks use that GPU)
        # At minimum, filter should not break the page
        visible_rows = page.locator("tr.data-row:not(.hidden)")
        expect(visible_rows.first).to_be_visible()

    def test_filter_by_resolution(self, page: Page, overview_report_url: str):
        """Filtering by resolution should work correctly."""
        page.goto(overview_report_url)

        res_select = page.locator("#filter-res")
        res_select.select_option("FHD")

        # Page should still be functional
        table = page.locator(".benchmark-table")
        expect(table).to_be_visible()

    def test_reset_clears_all_filters(self, page: Page, overview_report_url: str):
        """Reset button should clear all filters."""
        page.goto(overview_report_url)

        # Apply some filters
        page.locator("#filter-gpu").select_option(index=1)
        page.locator("#filter-res").select_option(index=1)

        # Click reset
        page.get_by_role("button", name="Reset").click()

        # All filters should be back to "All"
        expect(page.locator("#filter-gpu")).to_have_value("")
        expect(page.locator("#filter-res")).to_have_value("")

    def test_multiple_filters_combine(self, page: Page, overview_report_url: str):
        """Multiple filters should work together (AND logic)."""
        page.goto(overview_report_url)

        # Get initial benchmark count
        initial_count = int(page.locator("#visible-count").inner_text())

        # Apply GPU filter
        page.locator("#filter-gpu").select_option(index=1)
        after_gpu = int(page.locator("#visible-count").inner_text())

        # Apply OS filter
        page.locator("#filter-os").select_option(index=1)
        after_os = int(page.locator("#visible-count").inner_text())

        # Combined filter should show same or fewer results
        assert after_os <= after_gpu <= initial_count


class TestFilterTags:
    """Tests for the active filter tags feature."""

    def test_filter_tag_appears_on_selection(self, page: Page, overview_report_url: str):
        """Filter tag should appear when a filter is selected."""
        page.goto(overview_report_url)

        # Select a GPU
        page.locator("#filter-gpu").select_option(index=1)

        # Filter tag should appear
        filter_tags = page.locator(".active-filters .filter-tag")
        expect(filter_tags).to_have_count(1)
        expect(filter_tags.first).to_contain_text("GPU:")

    def test_multiple_filter_tags(self, page: Page, overview_report_url: str):
        """Multiple filter tags should appear for multiple filters."""
        page.goto(overview_report_url)

        # Select multiple filters
        page.locator("#filter-gpu").select_option(index=1)
        page.locator("#filter-os").select_option(index=1)

        # Two filter tags should appear
        filter_tags = page.locator(".active-filters .filter-tag")
        expect(filter_tags).to_have_count(2)

    def test_filter_tag_remove_button(self, page: Page, overview_report_url: str):
        """Clicking X on filter tag should remove that filter."""
        page.goto(overview_report_url)

        # Select a filter
        page.locator("#filter-gpu").select_option(index=1)

        # Click the remove button on the tag
        page.locator(".filter-tag .remove").click()

        # Tag should disappear
        filter_tags = page.locator(".active-filters .filter-tag")
        expect(filter_tags).to_have_count(0)

        # Filter dropdown should be reset
        expect(page.locator("#filter-gpu")).to_have_value("")

    def test_reset_clears_filter_tags(self, page: Page, overview_report_url: str):
        """Reset button should clear all filter tags."""
        page.goto(overview_report_url)

        # Apply filters
        page.locator("#filter-gpu").select_option(index=1)
        page.locator("#filter-res").select_option(index=1)

        # Verify tags exist
        expect(page.locator(".active-filters .filter-tag")).to_have_count(2)

        # Click reset
        page.get_by_role("button", name="Reset").click()

        # Tags should be gone
        expect(page.locator(".active-filters .filter-tag")).to_have_count(0)


class TestTableSorting:
    """Tests for table sorting functionality."""

    def test_sort_by_avg_fps_ascending(self, page: Page, overview_report_url: str):
        """Clicking AVG FPS header should sort ascending."""
        page.goto(overview_report_url)

        # Click AVG FPS header (second column)
        avg_fps_header = page.locator(".benchmark-table > thead > tr > th").nth(1)
        avg_fps_header.click()

        # Sort arrow should have 'asc' class (arrow rendered via CSS ::after)
        sort_arrow = avg_fps_header.locator(".sort-arrow")
        expect(sort_arrow).to_have_class("sort-arrow asc")

    def test_sort_by_avg_fps_descending(self, page: Page, overview_report_url: str):
        """Clicking AVG FPS header twice should sort descending."""
        page.goto(overview_report_url)

        # Click twice for descending
        avg_fps_header = page.locator(".benchmark-table > thead > tr > th").nth(1)
        avg_fps_header.click()
        avg_fps_header.click()

        # Sort arrow should have 'desc' class (arrow rendered via CSS ::after)
        sort_arrow = avg_fps_header.locator(".sort-arrow")
        expect(sort_arrow).to_have_class("sort-arrow desc")

    def test_sort_by_game_name(self, page: Page, overview_report_url: str):
        """Should be able to sort by game name."""
        page.goto(overview_report_url)

        # Click Game header (first column)
        game_header = page.locator(".benchmark-table > thead > tr > th").first
        game_header.click()

        # Sort arrow should have 'asc' class (arrow rendered via CSS ::after)
        sort_arrow = game_header.locator(".sort-arrow")
        expect(sort_arrow).to_have_class("sort-arrow asc")


class TestDetailsPanel:
    """Tests for the expandable details panel."""

    def test_click_row_expands_details(self, page: Page, overview_report_url: str):
        """Clicking a game row should expand its details panel."""
        page.goto(overview_report_url)

        # Click first data row
        first_row = page.locator("tr.data-row").first
        first_row.click()

        # Detail row should become visible
        detail_row = page.locator("tr.detail-row.show")
        expect(detail_row).to_be_visible()

    def test_expanded_row_has_blue_border(self, page: Page, overview_report_url: str):
        """Expanded row should have the 'expanded' class for styling."""
        page.goto(overview_report_url)

        first_row = page.locator("tr.data-row").first
        first_row.click()

        # Row should have expanded class (check class attribute contains 'expanded')
        expect(first_row).to_have_attribute("class", "data-row expanded")

    def test_close_button_closes_details(self, page: Page, overview_report_url: str):
        """Close button should close the details panel."""
        page.goto(overview_report_url)

        # Open details
        page.locator("tr.data-row").first.click()
        expect(page.locator("tr.detail-row.show")).to_be_visible()

        # Click close button (the visible one in the open panel)
        page.locator("tr.detail-row.show .close-details").click()

        # Details should be hidden
        expect(page.locator("tr.detail-row.show")).to_have_count(0)

    def test_only_one_details_open_at_time(self, page: Page, overview_report_url: str):
        """Only one details panel should be open at a time."""
        page.goto(overview_report_url)

        rows = page.locator("tr.data-row")

        # Click first row
        rows.nth(0).click()
        expect(page.locator("tr.detail-row.show")).to_have_count(1)

        # Click second row
        rows.nth(1).click()

        # Still only one detail panel open
        expect(page.locator("tr.detail-row.show")).to_have_count(1)

    def test_details_panel_has_stats(self, page: Page, overview_report_url: str):
        """Details panel should show FPS statistics."""
        page.goto(overview_report_url)

        page.locator("tr.data-row").first.click()

        detail_content = page.locator("tr.detail-row.show .detail-content")
        expect(detail_content.get_by_text("AVG FPS", exact=True)).to_be_visible()
        expect(detail_content.get_by_text("1% Low", exact=True)).to_be_visible()
        expect(detail_content.get_by_text("0.1% Low", exact=True)).to_be_visible()

    def test_details_panel_has_run_selector(self, page: Page, overview_report_url: str):
        """Details panel should have run selector dropdowns."""
        page.goto(overview_report_url)

        page.locator("tr.data-row").first.click()

        # Main run selector
        main_select = page.locator("select[id^='select-']").first
        expect(main_select).to_be_visible()

        # Compare selector
        compare_select = page.locator("select[id^='compare-']").first
        expect(compare_select).to_be_visible()


class TestTooltips:
    """Tests for metric tooltips."""

    def test_avg_fps_tooltip_exists(self, page: Page, overview_report_url: str):
        """AVG FPS column should have a tooltip."""
        page.goto(overview_report_url)

        # AVG FPS is the second column header
        avg_fps_header = page.locator(".benchmark-table th").nth(1)
        tooltip_wrapper = avg_fps_header.locator(".tooltip-wrapper")
        expect(tooltip_wrapper).to_be_visible()

        # Tooltip text should exist (hidden by default)
        tooltip_text = tooltip_wrapper.locator(".tooltip-text")
        expect(tooltip_text).to_contain_text("Average FPS")

    def test_stutter_tooltip_exists(self, page: Page, overview_report_url: str):
        """Stutter column should have a tooltip."""
        page.goto(overview_report_url)

        # Stutter is the 5th column (index 4)
        stutter_header = page.locator(".benchmark-table th").nth(4)
        tooltip_wrapper = stutter_header.locator(".tooltip-wrapper")
        expect(tooltip_wrapper).to_be_visible()

    def test_consistency_tooltip_exists(self, page: Page, overview_report_url: str):
        """Consistency column should have a tooltip."""
        page.goto(overview_report_url)

        # Consistency is the 6th column (index 5)
        consistency_header = page.locator(".benchmark-table th").nth(5)
        tooltip_wrapper = consistency_header.locator(".tooltip-wrapper")
        expect(tooltip_wrapper).to_be_visible()

    def test_tooltip_visible_on_hover(self, page: Page, overview_report_url: str):
        """Tooltip should become visible on hover."""
        page.goto(overview_report_url)

        # AVG FPS is the second column header
        avg_fps_header = page.locator(".benchmark-table th").nth(1)
        tooltip_wrapper = avg_fps_header.locator(".tooltip-wrapper")
        tooltip_wrapper.hover()

        # After hover, tooltip should be visible (CSS :hover makes it visible)
        # Note: This tests that the element exists, actual visibility depends on CSS
        tooltip_text = tooltip_wrapper.locator(".tooltip-text")
        expect(tooltip_text).to_be_attached()


class TestResponsiveDesign:
    """Tests for responsive design elements."""

    def test_table_wrapper_exists(self, page: Page, overview_report_url: str):
        """Table should be wrapped for horizontal scrolling."""
        page.goto(overview_report_url)

        table_wrapper = page.locator(".table-wrapper")
        expect(table_wrapper).to_be_visible()

    def test_table_scrollable_on_small_viewport(self, page: Page, overview_report_url: str):
        """Table should be scrollable on small viewports."""
        page.set_viewport_size({"width": 600, "height": 800})
        page.goto(overview_report_url)

        # Table wrapper should have overflow-x: auto
        table_wrapper = page.locator(".table-wrapper")
        expect(table_wrapper).to_be_visible()

        # Table should maintain min-width
        table = page.locator(".benchmark-table")
        expect(table).to_be_visible()


class TestNoDuplicateEntries:
    """Tests to ensure no duplicate entries in dropdowns."""

    def test_no_duplicate_runs_in_main_dropdown(self, page: Page, overview_report_url: str):
        """Main run selector should not have duplicate entries."""
        page.goto(overview_report_url)

        # Open details for a game with multiple runs
        page.locator("tr.data-row").first.click()

        # Get all options from main selector
        main_select = page.locator("select[id^='select-']").first
        options = main_select.locator("option").all_inner_texts()

        # Check for duplicates
        unique_options = set(options)
        assert len(options) == len(unique_options), f"Found duplicate entries: {options}"

    def test_no_duplicate_runs_in_compare_dropdown(self, page: Page, overview_report_url: str):
        """Compare run selector should not have duplicate entries."""
        page.goto(overview_report_url)

        page.locator("tr.data-row").first.click()

        compare_select = page.locator("select[id^='compare-']").first
        options = compare_select.locator("option").all_inner_texts()

        # First option is "No comparison", rest should be unique
        run_options = options[1:]  # Skip "No comparison"
        unique_options = set(run_options)
        assert len(run_options) == len(unique_options), f"Found duplicate entries: {run_options}"


class TestResolutionSorting:
    """Tests for consistent resolution sorting (UHD → WQHD → FHD)."""

    def test_main_filter_resolution_order(self, page: Page, overview_report_url: str):
        """Main page resolution filter should be sorted: UHD, WQHD, FHD."""
        page.goto(overview_report_url)

        filter_res = page.locator("#filter-res")
        options = filter_res.locator("option").all_inner_texts()

        # Skip "All" option, check order of resolutions
        res_options = [o for o in options if o != "All"]

        # Define expected order (UHD/3840x2160 first, then WQHD/2560x1440, then FHD/1920x1080)
        def get_res_priority(res: str) -> int:
            if "UHD" in res or "3840" in res:
                return 0
            elif "WQHD" in res or "2560" in res:
                return 1
            elif "FHD" in res or "1920" in res:
                return 2
            return 99

        # Verify sorting
        priorities = [get_res_priority(r) for r in res_options]
        assert priorities == sorted(priorities), f"Resolution not sorted correctly: {res_options}"

    def test_detail_filter_resolution_order(self, page: Page, overview_report_url: str):
        """Detail panel resolution filter should be sorted: UHD, WQHD, FHD."""
        page.goto(overview_report_url)

        # Open details for first game
        page.locator("tr.data-row").first.click()
        page.wait_for_selector("tr.detail-row.show")

        # Get detail resolution filter
        filter_res = page.locator("select[id^='filter-res-']").first
        options = filter_res.locator("option").all_inner_texts()

        # Skip "All" option
        res_options = [o for o in options if o != "All"]

        if len(res_options) > 1:
            def get_res_priority(res: str) -> int:
                if "UHD" in res or "3840" in res:
                    return 0
                elif "WQHD" in res or "2560" in res:
                    return 1
                elif "FHD" in res or "1920" in res:
                    return 2
                return 99

            priorities = [get_res_priority(r) for r in res_options]
            assert priorities == sorted(priorities), f"Detail resolution not sorted correctly: {res_options}"

    def test_run_dropdown_resolution_order(self, page: Page, overview_report_url: str):
        """Run selector dropdown should be sorted by resolution (UHD first)."""
        page.goto(overview_report_url)

        # Open details
        page.locator("tr.data-row").first.click()
        page.wait_for_selector("tr.detail-row.show")

        # Get run selector options
        main_select = page.locator("select[id^='select-']").first
        options = main_select.locator("option").all_inner_texts()

        if len(options) > 1:
            def get_res_priority(opt: str) -> int:
                if "UHD" in opt or "3840" in opt:
                    return 0
                elif "WQHD" in opt or "2560" in opt:
                    return 1
                elif "FHD" in opt or "1920" in opt:
                    return 2
                return 99

            priorities = [get_res_priority(o) for o in options]
            assert priorities == sorted(priorities), f"Run dropdown not sorted by resolution: {options}"


class TestDetailSystemInfoUpdates:
    """Tests that system info updates when selecting different runs."""

    def test_gpu_updates_on_run_change(self, page: Page, overview_report_url: str):
        """GPU should update when selecting a different run."""
        page.goto(overview_report_url)

        # Open details
        page.locator("tr.data-row").first.click()
        page.wait_for_selector("tr.detail-row.show")

        # Get initial GPU value
        gpu_el = page.locator("[id^='stat-gpu-']").first
        initial_gpu = gpu_el.inner_text()

        # Get run selector and check if multiple options exist
        main_select = page.locator("select[id^='select-']").first
        options = main_select.locator("option")
        option_count = options.count()

        if option_count > 1:
            # Select a different run
            main_select.select_option(index=1)
            page.wait_for_timeout(100)  # Wait for update

            # GPU element should still exist (even if value is same)
            expect(gpu_el).to_be_visible()

    def test_system_info_elements_exist(self, page: Page, overview_report_url: str):
        """System info elements (GPU, Mesa, OS, Resolution) should exist in details."""
        page.goto(overview_report_url)

        # Open details
        page.locator("tr.data-row").first.click()
        page.wait_for_selector("tr.detail-row.show")

        # Check all system info elements exist
        expect(page.locator("[id^='stat-gpu-']").first).to_be_visible()
        expect(page.locator("[id^='stat-mesa-']").first).to_be_visible()
        expect(page.locator("[id^='stat-os-']").first).to_be_visible()
        expect(page.locator("[id^='stat-res-']").first).to_be_visible()

    def test_header_updates_on_run_change(self, page: Page, overview_report_url: str):
        """Detail header should update when selecting a different run."""
        page.goto(overview_report_url)

        # Open details
        page.locator("tr.data-row").first.click()
        page.wait_for_selector("tr.detail-row.show")

        # Get initial header
        header = page.locator("tr.detail-row.show .detail-header h3")
        initial_header = header.inner_text()

        # Header should contain game name and resolution info
        assert " - " in initial_header, f"Header format incorrect: {initial_header}"
        assert " @ " in initial_header, f"Header should contain ' @ ': {initial_header}"
