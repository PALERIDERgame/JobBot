from __future__ import annotations

import unittest

from application_routing import assess_email_apply, infer_application_routing


class ApplicationRoutingTests(unittest.TestCase):
    def test_privacy_compliance_email_does_not_trigger_email_apply(self) -> None:
        description = """
        If you have questions, contact compliance@integralads.com.
        This inbox will not be monitored for application status updates.
        """
        routing = infer_application_routing(description, "https://www.indeed.com/viewjob?jk=1")
        self.assertEqual(routing.apply_method, "board")
        self.assertEqual(routing.hiring_manager_email, "")

    def test_explicit_send_resume_instruction_keeps_email_apply(self) -> None:
        description = "Please send your resume and cover letter to recruiting@example.com to apply."
        routing = infer_application_routing(description, "https://example.com/job")
        self.assertEqual(routing.apply_method, "email")
        self.assertEqual(routing.hiring_manager_email, "recruiting@example.com")

    def test_generic_contact_email_without_explicit_apply_instruction_is_blocked(self) -> None:
        description = "For questions, email recruiting@example.com."
        assessment = assess_email_apply(description, "https://example.com/job")
        self.assertFalse(assessment.is_explicit)
        self.assertEqual(assessment.confidence, "not present")
        self.assertIn("does not explicitly instruct", assessment.reason)
