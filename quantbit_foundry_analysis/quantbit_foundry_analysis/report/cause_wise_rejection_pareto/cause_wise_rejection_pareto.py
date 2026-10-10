# Copyright (c) 2026, Quantbit Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from collections import defaultdict


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data, chart, report_summary = get_data(filters)
	message = get_message()
	return columns, data, message, chart, report_summary


def get_columns():
	return [
		{
			"fieldname": "cause",
			"label": _("Cause"),
			"fieldtype": "Data",
			"width": 220,
		},
		{
			"fieldname": "rejection_weight",
			"label": _("Rejection Weight (kg)"),
			"fieldtype": "Float",
			"precision": 3,
			"width": 180,
		},
		{
			"fieldname": "cumulative_percent",
			"label": _("Cumulative %"),
			"fieldtype": "Percent",
			"precision": 1,
			"width": 140,
		},
		{
			"fieldname": "threshold",
			"label": _("80% Threshold"),
			"fieldtype": "Percent",
			"precision": 1,
			"width": 140,
		},
	]


def get_message():
	return _("Bars = Rejection Weight / Line = Cumulative % / 80% = focus threshold")


def get_data(filters):
	company = filters.get("company")
	from_date = filters.get("from_date")
	to_date = filters.get("to_date")
	item_code = filters.get("item_code")
	rejection_type = (filters.get("casting_treatment_rejection_type") or filters.get("type") or "").strip().lower()
	rejection_reason = filters.get("casting_treatment_rejection_reason") or filters.get("reason")

	# Base filter conditions
	inhouse_conditions = ["ct.docstatus = 1"]
	foundry_conditions = [
		"fra.docstatus = 1",
		"fraa.document_type IN ('Subcontracting In', 'Sales Invoice')",
	]

	query_params = {}
	if from_date and to_date:
		inhouse_conditions.append("ct.treatment_date BETWEEN %(from_date)s AND %(to_date)s")
		foundry_conditions.append("fra.posting_date BETWEEN %(from_date)s AND %(to_date)s")
		query_params["from_date"] = from_date
		query_params["to_date"] = to_date

	if company:
		inhouse_conditions.append("ct.company = %(company)s")
		foundry_conditions.append("fra.company = %(company)s")
		query_params["company"] = company

	if item_code:
		inhouse_conditions.append("ctrd.casting_item_code = %(item_code)s")
		foundry_conditions.append("frad.casting_item_code = %(item_code)s")
		query_params["item_code"] = item_code

	if rejection_reason:
		inhouse_conditions.append("ctrd.casting_treatment_rejection_reason = %(rejection_reason)s")
		foundry_conditions.append("frad.casting_treatment_rejection_reason = %(rejection_reason)s")
		query_params["rejection_reason"] = rejection_reason

	fetch_inhouse = True
	fetch_foundry = True

	if rejection_type:
		if rejection_type in ["inhouse", "in-house"]:
			fetch_foundry = False
		elif rejection_type == "subcontracting":
			fetch_inhouse = False
			foundry_conditions.append("fraa.document_type = 'Subcontracting In'")
		elif rejection_type == "customer":
			fetch_inhouse = False
			foundry_conditions.append("fraa.document_type = 'Sales Invoice'")
		else:
			inhouse_conditions.append("ctrd.casting_treatment_rejection_type = %(rejection_type)s")
			foundry_conditions.append("frad.casting_treatment_rejection_type = %(rejection_type)s")
			query_params["rejection_type"] = rejection_type

	inhouse_data = []
	foundry_data = []

	if fetch_inhouse:
		inhouse_where = " AND ".join(inhouse_conditions)
		inhouse_data = frappe.db.sql(
			f"""
			SELECT
				COALESCE(ctrd.casting_treatment_rejection_reason, 'Not Specified') AS rejection_reason,
				SUM(ctrd.total_weight) AS inhouse_weight
			FROM `tabCasting Treatment` ct
			JOIN `tabCasting Treatment Rejected Reasons Details` ctrd ON ctrd.parent = ct.name
			WHERE {inhouse_where}
			GROUP BY ctrd.casting_treatment_rejection_reason
			""",
			query_params,
			as_dict=True,
		)

	if fetch_foundry:
		foundry_where = " AND ".join(foundry_conditions)
		foundry_data = frappe.db.sql(
			f"""
			SELECT
				COALESCE(frad.casting_treatment_rejection_reason, 'Not Specified') AS rejection_reason,
				SUM(frad.total_weight) AS foundry_weight
			FROM `tabFoundry Rejection Analysis` fra
			JOIN `tabFoundry Rejection Analysis Rejected Reasons` frad ON frad.parent = fra.name
			JOIN `tabFoundary Rejection Analysis Details` fraa ON fra.name = fraa.parent
			WHERE {foundry_where}
			GROUP BY frad.casting_treatment_rejection_reason
			""",
			query_params,
			as_dict=True,
		)

	cause_weights = defaultdict(float)
	for row in inhouse_data:
		cause = (row.rejection_reason or "").strip() or "Not Specified"
		cause_weights[cause] += flt(row.inhouse_weight)

	for row in foundry_data:
		cause = (row.rejection_reason or "").strip() or "Not Specified"
		cause_weights[cause] += flt(row.foundry_weight)

	# Filter out 0 or negative weights and sort descending (Pareto ordering)
	sorted_causes = sorted(
		[(cause, weight) for cause, weight in cause_weights.items() if weight > 0],
		key=lambda x: x[1],
		reverse=True,
	)

	grand_total_weight = sum(w for _, w in sorted_causes)

	data = []
	cumulative_weight = 0.0
	vital_few_count = 0

	for cause, weight in sorted_causes:
		cumulative_weight += weight
		cum_percent = (cumulative_weight / grand_total_weight * 100.0) if grand_total_weight else 0.0
		cum_percent = round(cum_percent, 1)

		if cum_percent <= 80.0 or (vital_few_count == 0 and cum_percent > 80.0):
			vital_few_count += 1
		elif cumulative_weight - weight < (0.8 * grand_total_weight):
			vital_few_count += 1

		data.append(
			{
				"cause": cause,
				"rejection_weight": round(weight, 3),
				"cumulative_percent": cum_percent,
				"threshold": 80.0,
			}
		)

	chart = get_chart_data(data)
	report_summary = get_report_summary(grand_total_weight, len(data), vital_few_count)

	return data, chart, report_summary


def get_chart_data(data):
	if not data:
		return None

	labels = [row["cause"] for row in data]
	weights = [row["rejection_weight"] for row in data]
	cumulative_percentages = [row["cumulative_percent"] for row in data]
	thresholds = [row["threshold"] for row in data]

	chart = {
		"data": {
			"labels": labels,
			"datasets": [
				{
					"name": _("Rejection Weight (kg)"),
					"values": weights,
					"chartType": "bar",
				},
				{
					"name": _("Cumulative %"),
					"values": cumulative_percentages,
					"chartType": "line",
				},
				{
					"name": _("80% Threshold"),
					"values": thresholds,
					"chartType": "line",
				},
			],
			"yMarkers": [
				{
					"label": _("80% Threshold"),
					"value": 80,
					"options": {"labelPos": "right"},
				}
			],
		},
		"type": "axis-mixed",
		"colors": ["#3b82f6", "#ef4444", "#10b981"],
		"axisOptions": {
			"xIsSeries": 1,
			"shortenYAxisNumbers": 1,
		},
	}
	return chart


def get_report_summary(total_weight, total_causes, vital_few_count):
	return [
		{
			"value": round(total_weight, 3),
			"indicator": "Blue",
			"label": _("Total Rejection Weight (kg)"),
			"datatype": "Float",
		},
		{
			"value": total_causes,
			"indicator": "Orange",
			"label": _("Total Causes"),
			"datatype": "Int",
		},
		{
			"value": vital_few_count,
			"indicator": "Green",
			"label": _("Causes in 80% Threshold"),
			"datatype": "Int",
		},
	]


def flt(val):
	try:
		return float(val or 0)
	except (ValueError, TypeError):
		return 0.0


@frappe.whitelist()
def get_dashboard_data(filters=None):
	if isinstance(filters, str):
		try:
			filters = frappe.parse_json(filters)
		except Exception:
			pass
	filters = filters or {}

	if not filters.get("company"):
		filters["company"] = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
	if not filters.get("from_date"):
		filters["from_date"] = frappe.utils.add_months(frappe.utils.today(), -3)
	if not filters.get("to_date"):
		filters["to_date"] = frappe.utils.today()

	company = filters.get("company")
	from_date = filters.get("from_date")
	to_date = filters.get("to_date")
	item_code = filters.get("item_code")
	rejection_type = (filters.get("casting_treatment_rejection_type") or filters.get("type") or "").strip().lower()
	rejection_reason = filters.get("casting_treatment_rejection_reason") or filters.get("reason")

	# 1. Pouring Production records
	prod_conditions = [
		"p.docstatus = 1",
		"p.heat_date BETWEEN %(from_date)s AND %(to_date)s"
	]
	prod_params = {
		"from_date": from_date,
		"to_date": to_date
	}
	if company:
		prod_conditions.append("p.company = %(company)s")
		prod_params["company"] = company
	if item_code:
		prod_conditions.append("pcd.casting_item_code = %(item_code)s")
		prod_params["item_code"] = item_code

	prod_where = " AND ".join(prod_conditions)
	prod_rows = frappe.db.sql(f"""
		SELECT
			DATE_FORMAT(p.heat_date, '%%Y-%%m-%%d') AS date,
			pcd.casting_item_code AS item,
			ROUND(SUM(pcd.total_weight), 2) AS weight
		FROM `tabPouring Casting Details` pcd
		JOIN `tabPouring` p ON p.name = pcd.parent
		WHERE {prod_where}
		GROUP BY p.heat_date, pcd.casting_item_code
	""", prod_params, as_dict=True)

	# 2. Rejection records
	fetch_inhouse = not rejection_type or rejection_type in ["inhouse", "in-house", "all"]
	fetch_foundry = not rejection_type or rejection_type in ["subcontracting", "customer", "all"]

	rejection_rows = []

	if fetch_inhouse:
		in_conditions = [
			"ct.docstatus = 1",
			"ct.treatment_date BETWEEN %(from_date)s AND %(to_date)s"
		]
		in_params = {"from_date": from_date, "to_date": to_date}
		if company:
			in_conditions.append("ct.company = %(company)s")
			in_params["company"] = company
		if item_code:
			in_conditions.append("ctrd.casting_item_code = %(item_code)s")
			in_params["item_code"] = item_code
		if rejection_reason:
			in_conditions.append("ctrd.casting_treatment_rejection_reason = %(rejection_reason)s")
			in_params["rejection_reason"] = rejection_reason

		in_where = " AND ".join(in_conditions)
		inhouse_data = frappe.db.sql(f"""
			SELECT
				DATE_FORMAT(ct.treatment_date, '%%Y-%%m-%%d') AS date,
				ctrd.casting_item_code AS item,
				'inhouse' AS type,
				COALESCE(NULLIF(TRIM(ctrd.casting_treatment_rejection_reason), ''), 'Not Specified') AS cause,
				ROUND(SUM(ctrd.total_weight), 2) AS weight
			FROM `tabCasting Treatment` ct
			JOIN `tabCasting Treatment Rejected Reasons Details` ctrd ON ctrd.parent = ct.name
			WHERE {in_where}
			GROUP BY ct.treatment_date, ctrd.casting_item_code, ctrd.casting_treatment_rejection_reason
		""", in_params, as_dict=True)
		for r in inhouse_data:
			rejection_rows.append({
				"date": str(r["date"]),
				"item": r["item"],
				"type": "inhouse",
				"cause": r["cause"],
				"weight": flt(r["weight"])
			})

	if fetch_foundry:
		fd_conditions = [
			"fra.docstatus = 1",
			"fra.posting_date BETWEEN %(from_date)s AND %(to_date)s",
			"fraa.document_type IN ('Subcontracting In', 'Sales Invoice')"
		]
		fd_params = {"from_date": from_date, "to_date": to_date}
		if company:
			fd_conditions.append("fra.company = %(company)s")
			fd_params["company"] = company
		if item_code:
			fd_conditions.append("frad.casting_item_code = %(item_code)s")
			fd_params["item_code"] = item_code
		if rejection_reason:
			fd_conditions.append("frad.casting_treatment_rejection_reason = %(rejection_reason)s")
			fd_params["rejection_reason"] = rejection_reason

		if rejection_type == "subcontracting":
			fd_conditions.append("fraa.document_type = 'Subcontracting In'")
		elif rejection_type == "customer":
			fd_conditions.append("fraa.document_type = 'Sales Invoice'")

		fd_where = " AND ".join(fd_conditions)
		foundry_data = frappe.db.sql(f"""
			SELECT
				DATE_FORMAT(fra.posting_date, '%%Y-%%m-%%d') AS date,
				frad.casting_item_code AS item,
				CASE
					WHEN fraa.document_type = 'Subcontracting In' THEN 'subcontracting'
					ELSE 'customer'
				END AS type,
				COALESCE(NULLIF(TRIM(frad.casting_treatment_rejection_reason), ''), 'Not Specified') AS cause,
				ROUND(SUM(frad.total_weight), 2) AS weight
			FROM `tabFoundry Rejection Analysis` fra
			JOIN `tabFoundry Rejection Analysis Rejected Reasons` frad ON frad.parent = fra.name
			JOIN `tabFoundary Rejection Analysis Details` fraa ON fra.name = fraa.parent
			WHERE {fd_where}
			GROUP BY fra.posting_date, frad.casting_item_code, fraa.document_type, frad.casting_treatment_rejection_reason
		""", fd_params, as_dict=True)
		for r in foundry_data:
			rejection_rows.append({
				"date": str(r["date"]),
				"item": r["item"],
				"type": r["type"],
				"cause": r["cause"],
				"weight": flt(r["weight"])
			})

	production_data = []
	for p in prod_rows:
		production_data.append({
			"date": str(p["date"]),
			"item": p["item"],
			"weight": flt(p["weight"])
		})

	# 3. Pareto summary data
	pareto_data, chart, report_summary = get_data(filters)

	# 4. Filter lists for UI dropdowns
	items_set = set()
	causes_set = set()
	for p in production_data:
		if p.get("item"):
			items_set.add(p["item"])
	for r in rejection_rows:
		if r.get("item"):
			items_set.add(r["item"])
		if r.get("cause"):
			causes_set.add(r["cause"])

	total_production_weight = sum(p["weight"] for p in production_data)
	total_rejection_weight = sum(r["weight"] for r in rejection_rows)

	try:
		companies = [c.name for c in frappe.get_all("Company", fields=["name"])]
	except Exception:
		companies = []

	return {
		"production": production_data,
		"rejections": rejection_rows,
		"items": sorted(list(items_set)),
		"causes": sorted(list(causes_set)),
		"companies": companies,
		"selected_filters": filters,
		"pareto_data": pareto_data,
		"summary": {
			"total_production": round(total_production_weight, 2),
			"total_rejection": round(total_rejection_weight, 2),
			"rejection_percentage": round((total_rejection_weight / total_production_weight * 100), 2) if total_production_weight > 0 else 0.0,
		}
	}


@frappe.whitelist()
def sync_web_page():
	path = frappe.get_app_path("quantbit_foundry_analysis", "quantbit_foundry_analysis", "report", "cause_wise_rejection_pareto", "cause_wise_rejection_pareto.html")
	with open(path, "r", encoding="utf-8") as f:
		html = f.read()
	if frappe.db.exists("Web Page", "cause-wise-rejection-pareto"):
		frappe.db.set_value("Web Page", "cause-wise-rejection-pareto", "main_section_html", html)
		frappe.db.commit()
		return "Synced"
	return "Web Page not found"

