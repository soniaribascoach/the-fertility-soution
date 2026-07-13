"""The paused-lead email carve-out (worker). Pure, no DB, no LLM.

After the booking link the brain pauses on anything that is not "I booked" or an
email. That means a lead who replies "ok thanks!" (pausing the AI) and only THEN
sends her email would be skipped by the worker and her email lost. The worker
lets exactly that one message through.
"""
from app.worker import contains_email


def test_detects_an_email_anywhere_in_the_message():
    assert contains_email(["Here's the email i booked with asjad@mail.com"])
    assert contains_email(["sarah.jones+tag@gmail.co.uk"])
    assert contains_email(["ok thanks", "my email is a@b.io"])  # batched messages


def test_ignores_messages_without_one():
    assert not contains_email(["awesome, thank you sonia"])
    assert not contains_email(["ok i will thanks"])
    assert not contains_email([""])
    assert not contains_email([None])
    # An @handle is not an email address.
    assert not contains_email(["find me @soniaribas"])
