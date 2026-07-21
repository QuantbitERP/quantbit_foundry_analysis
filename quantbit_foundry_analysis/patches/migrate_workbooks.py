import frappe


def execute():
	workbooks_data = [
		{"id": "2", "title": "Sales Order Analysis"},
		{"id": "3", "title": "Sales Workbook"},
		{"id": "4", "title": "Foundry Production"},
		{"id": "6", "title": "Machining Shop Analysis"}
	]

	doctypes_to_update = [
		"Insights Query", "Insights Chart", "Insights Dashboard",
		"Insights Query v3", "Insights Chart v3", "Insights Dashboard v3"
	]

	for wb in workbooks_data:
		wb_id = wb["id"]
		wb_title = wb["title"]

		if not frappe.db.exists("Insights Workbook", wb_id):
			frappe.db.sql(f"""
				INSERT INTO `tabInsights Workbook` (name, title, creation, modified, modified_by, owner, docstatus)
				VALUES ('{wb_id}', '{wb_title}', NOW(), NOW(), 'Administrator', 'Administrator', 0)
			""")
		else:
			frappe.db.set_value("Insights Workbook", wb_id, "title", wb_title)

		workbooks_with_title = frappe.get_all("Insights Workbook", filters={"title": wb_title}, pluck="name")
		
		for old_wb_id in workbooks_with_title:
			if str(old_wb_id) != str(wb_id):
				for doctype in doctypes_to_update:
					if frappe.db.exists("DocType", doctype):
						if frappe.get_meta(doctype).has_field("workbook"):
							records = frappe.get_all(doctype, filters={"workbook": old_wb_id}, pluck="name")
							for rec in records:
								frappe.db.set_value(doctype, rec, "workbook", wb_id)

				try:
					frappe.delete_doc("Insights Workbook", old_wb_id, ignore_permissions=True, force=True)
				except Exception:
					frappe.log_error(f"Failed to delete Insights Workbook {old_wb_id}", "quantbit_foundry_analysis migration")
