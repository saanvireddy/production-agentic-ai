"""Generate the sample policy PDFs used by the RAG pipeline.

The company ("Helix Dynamics") and every policy in here are fictional. The PDFs are
committed to the repo, so you only need to re-run this if you change the text:

    python scripts/generate_sample_docs.py
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "documents"

# Each document is a list of pages; each page is a list of (heading, body) sections.
DOCUMENTS: dict[str, dict] = {
    "employee_handbook.pdf": {
        "title": "Helix Dynamics Employee Handbook",
        "pages": [
            [
                (
                    "1. Welcome",
                    "This handbook describes how we work at Helix Dynamics. It applies to all "
                    "full-time and part-time employees in every office: Atlanta, Austin, Chicago, Denver and "
                    "remote locations. Where a dedicated policy exists (remote work, benefits, leave, security), "
                    "that policy takes precedence over this summary.",
                ),
                (
                    "2. Working Hours",
                    "Standard working hours are 9:00 AM to 5:00 PM local time, Monday through "
                    "Friday. Core collaboration hours are 10:00 AM to 3:00 PM Eastern Time, during which employees "
                    "are expected to be reachable. Non-exempt employees must record all hours worked in the "
                    "timekeeping system by the end of each week.",
                ),
            ],
            [
                (
                    "3. Code of Conduct",
                    "Employees must treat colleagues, customers and partners with respect. "
                    "Harassment, discrimination and retaliation of any kind are prohibited. Concerns can be raised "
                    "with a manager, with People Operations, or anonymously through the Ethics Hotline.",
                ),
                (
                    "4. Probation Period",
                    "New employees complete a 90-day introductory period. During this period "
                    "the employee and manager hold check-ins at 30, 60 and 90 days. Employees are eligible for "
                    "benefits from their first day, but remote work eligibility begins after the introductory "
                    "period.",
                ),
                (
                    "5. Performance Reviews",
                    "Performance reviews are held twice a year, in March and September. "
                    "Merit increases are awarded once a year after the September review cycle and take effect on "
                    "October 1.",
                ),
            ],
            [
                (
                    "6. Expenses",
                    "Business expenses must be submitted within 30 days with itemized receipts. "
                    "Meals while travelling are reimbursed up to 75 US dollars per day. Economy class is required "
                    "for flights under 6 hours.",
                ),
                (
                    "7. Equipment",
                    "Every employee receives a company laptop. Employees who work remotely at least "
                    "two days a week receive a one-time home office stipend of 500 US dollars. Equipment must be "
                    "returned within 5 business days of separation.",
                ),
            ],
        ],
    },
    "remote_work_policy.pdf": {
        "title": "Helix Dynamics Remote Work Policy",
        "pages": [
            [
                (
                    "1. Purpose",
                    "This policy defines who can work remotely, how often, and the expectations that "
                    "apply while working outside a Helix Dynamics office.",
                ),
                (
                    "2. Eligibility",
                    "Employees become eligible for remote work after completing the 90-day "
                    "introductory period and must have a performance rating of 'Meets Expectations' or higher. "
                    "Roles that require on-site equipment, such as lab technicians and facilities staff, are not "
                    "eligible.",
                ),
            ],
            [
                (
                    "3. Hybrid Schedule",
                    "Eligible employees may work remotely up to three days per week. Tuesday "
                    "and Wednesday are anchor days on which all hybrid employees are expected in the office. The "
                    "remote days must be agreed with the manager and recorded in the HR system.",
                ),
                (
                    "4. Fully Remote Roles",
                    "Fully remote arrangements require approval from the department Vice "
                    "President and People Operations. Fully remote employees must travel to their home office for "
                    "the quarterly planning week, and travel costs for that week are covered by the company.",
                ),
            ],
            [
                (
                    "5. Work From Abroad",
                    "Employees may work from outside the country for up to 20 working days per "
                    "calendar year with at least two weeks' notice to their manager and People Operations. Working "
                    "from abroad for longer requires a tax and legal review.",
                ),
                (
                    "6. Home Office Requirements",
                    "Remote employees must have a private workspace and an internet "
                    "connection of at least 50 Mbps download. Company data may only be accessed over the corporate "
                    "VPN. Public Wi-Fi may not be used without the VPN.",
                ),
            ],
        ],
    },
    "benefits_policy.pdf": {
        "title": "Helix Dynamics Benefits Policy",
        "pages": [
            [
                (
                    "1. Health Insurance",
                    "Helix Dynamics offers medical, dental and vision coverage. The company "
                    "pays 90 percent of the premium for employees and 70 percent for dependents. Coverage begins on "
                    "the first day of employment.",
                ),
                (
                    "2. Retirement Plan",
                    "Employees can contribute to the 401(k) plan from their first paycheck. The "
                    "company matches 100 percent of the first 4 percent of salary contributed. Company matching "
                    "contributions vest fully after 2 years of service.",
                ),
            ],
            [
                (
                    "3. Learning and Development",
                    "Each employee has an annual learning budget of 2,000 US dollars "
                    "for courses, certifications and conferences. Unused budget does not roll over to the next "
                    "year. Certification exam fees for approved cloud and security certifications are reimbursed "
                    "in full and do not count against the learning budget.",
                ),
                (
                    "4. Wellness",
                    "Employees receive a monthly wellness stipend of 50 US dollars that can be used "
                    "for gym memberships, fitness classes or wellness apps.",
                ),
            ],
            [
                (
                    "5. Commuter Benefits",
                    "Employees who commute to an office can set aside pre-tax income for "
                    "transit and parking, up to the limits set by the IRS.",
                ),
                (
                    "6. Employee Assistance Program",
                    "The Employee Assistance Program provides free, confidential "
                    "counselling sessions, up to 8 sessions per issue per year, for employees and their household "
                    "members.",
                ),
            ],
        ],
    },
    "leave_policy.pdf": {
        "title": "Helix Dynamics Leave Policy",
        "pages": [
            [
                (
                    "1. Paid Time Off (Vacation)",
                    "Vacation accrues according to years of service. Employees with "
                    "less than 2 years of service receive 15 days of paid vacation per year. Employees with 2 to 5 "
                    "years of service receive 20 days per year. Employees with more than 5 years of service receive "
                    "25 days of paid vacation per year.",
                ),
                (
                    "2. Carryover",
                    "Up to 5 unused vacation days may be carried over into the next calendar year. "
                    "Carried-over days must be used by March 31, after which they expire.",
                ),
            ],
            [
                (
                    "3. Sick Leave",
                    "All employees receive 10 days of paid sick leave per year, separate from "
                    "vacation. A doctor's note is required only for absences longer than 3 consecutive days.",
                ),
                (
                    "4. Parental Leave",
                    "Birthing parents receive 16 weeks of fully paid parental leave. "
                    "Non-birthing parents receive 12 weeks of fully paid parental leave. Parental leave must be "
                    "taken within 12 months of the birth or adoption.",
                ),
            ],
            [
                (
                    "5. Holidays",
                    "Helix Dynamics observes 11 paid company holidays per year, plus 2 floating "
                    "holidays that employees can use on days of personal significance.",
                ),
                (
                    "6. Sabbatical",
                    "Employees who complete 7 years of continuous service are eligible for a 4-week "
                    "paid sabbatical, which must be taken within 12 months of becoming eligible.",
                ),
            ],
        ],
    },
    "security_policy.pdf": {
        "title": "Helix Dynamics Information Security Policy",
        "pages": [
            [
                (
                    "1. Passwords and MFA",
                    "Passwords must be at least 14 characters long. Multi-factor "
                    "authentication is mandatory for email, VPN, source control and all cloud consoles. Passwords "
                    "must be stored in the company password manager and never shared.",
                ),
                (
                    "2. Data Classification",
                    "Company data is classified as Public, Internal, Confidential or "
                    "Restricted. Customer data and employee salary data are Restricted and may only be stored in "
                    "approved systems with encryption at rest.",
                ),
            ],
            [
                (
                    "3. Device Security",
                    "Laptops must use full-disk encryption and lock automatically after 5 "
                    "minutes of inactivity. Operating system security updates must be installed within 14 days of "
                    "release.",
                ),
                (
                    "4. Incident Reporting",
                    "Suspected security incidents, including lost devices and phishing "
                    "emails, must be reported to the Security team within 1 hour of discovery through the "
                    "#security-incidents channel or security@helixdynamics.example.",
                ),
            ],
            [
                (
                    "5. Access Reviews",
                    "Managers review access to production systems every quarter. Access is "
                    "removed within 24 hours of an employee leaving the company.",
                ),
                (
                    "6. Security Training",
                    "All employees must complete security awareness training within 30 days "
                    "of joining and annually thereafter. Engineers must also complete secure coding training every "
                    "year.",
                ),
            ],
        ],
    },
}


def build_pdf(filename: str, spec: dict) -> Path:
    styles = getSampleStyleSheet()
    path = OUT_DIR / filename
    doc = SimpleDocTemplate(str(path), pagesize=LETTER, title=spec["title"], author="Helix Dynamics (fictional)")
    story = [Paragraph(spec["title"], styles["Title"]), Spacer(1, 12)]
    for i, page in enumerate(spec["pages"]):
        if i:
            story.append(PageBreak())
        for heading, body in page:
            story.append(Paragraph(heading, styles["Heading2"]))
            story.append(Paragraph(body, styles["BodyText"]))
            story.append(Spacer(1, 10))
    doc.build(story)
    return path


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, spec in DOCUMENTS.items():
        print(f"wrote {build_pdf(name, spec)}")


if __name__ == "__main__":
    main()
