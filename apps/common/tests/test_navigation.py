from django.test import SimpleTestCase

from apps.common.navigation import build_sidebar_navigation, iter_navigation_groups


class SidebarAssemblyTests(SimpleTestCase):
    def test_declaration_keys_are_stripped_before_unfold_sees_them(self):
        groups = build_sidebar_navigation(None)

        self.assertGreater(len(groups), 0)
        for group in groups:
            self.assertNotIn("order", group)
            for item in group["items"]:
                self.assertNotIn("feature", item)

    def test_iter_yields_declarations_with_their_owning_app(self):
        declared = {slug for app, group in iter_navigation_groups() for slug in []}
        seen_apps = {app for app, _group in iter_navigation_groups()}

        self.assertIn("apps.accounts", seen_apps)
        self.assertIn("apps.access", seen_apps)
