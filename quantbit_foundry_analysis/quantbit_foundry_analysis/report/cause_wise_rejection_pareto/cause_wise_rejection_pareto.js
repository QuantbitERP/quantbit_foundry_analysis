// Copyright (c) 2026, Quantbit Technologies Pvt Ltd and contributors
// For license information, please see license.txt

frappe.query_reports["Cause-wise Rejection Pareto"] = {
	"filters": [
		{
			"fieldname": "company",
			"label": __("Company"),
			"fieldtype": "Link",
			"options": "Company",
			"default": frappe.defaults.get_user_default("Company"),
			"reqd": 1
		},
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.add_months(frappe.datetime.get_today(), -3),
			"reqd": 1
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today(),
			"reqd": 1
		},
		{
			"fieldname": "item_code",
			"label": __("Item"),
			"fieldtype": "Link",
			"options": "Item"
		},
		{
			"fieldname": "casting_treatment_rejection_type",
			"label": __("Rejection Type"),
			"fieldtype": "Select",
			"options": [
				{ "label": __("All Types"), "value": "" },
				{ "label": __("InHouse"), "value": "inhouse" },
				{ "label": __("Subcontracting"), "value": "subcontracting" },
				{ "label": __("Customer"), "value": "customer" }
			]
		},
		{
			"fieldname": "casting_treatment_rejection_reason",
			"label": __("Rejection Reason"),
			"fieldtype": "Link",
			"options": "Casting Treatment Rejection Reason Master"
		}
	],

	"onload": function (report) {
		// Embed the Foundry Analytics Dashboard container above the report datatable
		if (!report.page.main.find("#foundry-analytics-dashboard-slot").length) {
			const $slot = $(`
				<div id="foundry-analytics-dashboard-slot" style="margin-bottom: 24px;"></div>
			`);
			$slot.insertBefore(report.page.main.find(".report-wrapper"));
		}

		// Add quick toggle button to show/hide the visual dashboard
		report.page.add_inner_button(__("Toggle Charts Dashboard"), function () {
			$("#foundry-analytics-dashboard-slot").slideToggle(200);
		});
	},

	"after_datatable_render": function (report) {
		const filters = frappe.query_report ? frappe.query_report.get_values() : {};
		const $slot = $("#foundry-analytics-dashboard-slot");

		if (!$slot.length) return;

		// Fetch and render the dashboard with the active report filter values
		frappe.call({
			method: "quantbit_foundry_analysis.quantbit_foundry_analysis.report.cause_wise_rejection_pareto.cause_wise_rejection_pareto.get_dashboard_data",
			args: { filters: filters },
			callback: function (r) {
				if (!r || !r.message) return;

				if (window.FoundryDashboard && typeof window.FoundryDashboard.setData === "function" && $slot.find("#fad-pareto").length) {
					window.FoundryDashboard.setData(r.message);
				} else {
					// Load the HTML component into the slot
					frappe.call({
						method: "frappe.client.get_value",
						args: {
							doctype: "Report",
							filters: { name: "Cause-wise Rejection Pareto" },
							fieldname: "name"
						},
						callback: function () {
							fetch("/assets/quantbit_foundry_analysis/report/cause_wise_rejection_pareto/cause_wise_rejection_pareto.html")
								.then(res => {
									if (res.ok) return res.text();
									throw new Error("HTTP " + res.status);
								})
								.then(html => {
									$slot.html(html);
									if (window.FoundryDashboard) {
										window.FoundryDashboard.setData(r.message);
									}
								})
								.catch(() => {
									// Direct render fallback if asset URL differs
									renderInlineDashboard($slot, r.message);
								});
						}
					});
				}
			}
		});
	},

	"get_chart_data": function (columns, result) {
		if (!result || !result.length) {
			return null;
		}

		let labels = [];
		let weights = [];
		let cumulative_percentages = [];
		let thresholds = [];

		result.forEach((row) => {
			if (row.cause) {
				labels.push(row.cause);
				weights.push(row.rejection_weight || 0);
				cumulative_percentages.push(row.cumulative_percent || 0);
				thresholds.push(row.threshold || 80.0);
			}
		});

		return {
			data: {
				labels: labels,
				datasets: [
					{
						name: __("Rejection Weight (kg)"),
						values: weights,
						chartType: "bar"
					},
					{
						name: __("Cumulative %"),
						values: cumulative_percentages,
						chartType: "line"
					},
					{
						name: __("80% Threshold"),
						values: thresholds,
						chartType: "line"
					}
				],
				yMarkers: [
					{
						label: __("80% Threshold"),
						value: 80,
						options: { labelPos: "right" }
					}
				]
			},
			type: "axis-mixed",
			colors: ["#3b82f6", "#ef4444", "#10b981"],
			axisOptions: {
				xIsSeries: 1,
				shortenYAxisNumbers: 1
			}
		};
	},

	"formatter": function (value, row, column, data, default_formatter) {
		let formatted_value = default_formatter(value, row, column, data);

		if (column.fieldname === "cumulative_percent" && data) {
			if (data.cumulative_percent <= 80.0) {
				formatted_value = `<span style="color: #d9534f; font-weight: 600;">${formatted_value}</span>`;
			}
		}

		return formatted_value;
	}
};

function renderInlineDashboard($container, data) {
	if (!window.FoundryDashboard) return;
	window.FoundryDashboard.setData(data);
}
