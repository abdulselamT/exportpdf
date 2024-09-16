/** @odoo-module */
import {ListController} from '@web/views/list/list_controller'
import {patch} from "@web/core/utils/patch";
import { useService, useBus } from "@web/core/utils/hooks";
import { extractFieldsFromArchInfo } from "@web/model/relational_model/utils";
import { download } from "@web/core/network/download";

patch(ListController.prototype,{
    setup(){
        super.setup();
        useBus(this.env.searchModel, "direct-export-pdf-data", this.onDirectExportpdf.bind(this));
    },
    async onDirectExportpdf(){

        const resp = await this.rpc("/get_pdf_data", {
            context: this.props.context,
            domain: this.model.root.domain,
            fields: this.defaultExportList,
            groupby: this.model.root.groupBy,
            model: this.model.root.resModel,
        })
        await this.actionService.doAction({
            type: "ir.actions.report",
            report_type: "qweb-html",
            report_name:"exportpdf.export_pdf",
            report_file: resp.model_description,
            data: {
                data:resp.data,
                headers:resp.labels,
                groupby:this.model.root.groupBy,
                is_pivot:false,
                display_name: resp.model_description,
            },
            context:{},
            display_name: resp.model_description,
            attachment_use:false
        });
    },
    async downloadExport(fields, import_compat, format) {
        let ids = false;
        if (!this.isDomainSelected) {
            const resIds = await this.getSelectedResIds();
            ids = resIds.length > 0 && resIds;
        }
        const exportedFields = fields.map((field) => ({
            name: field.name || field.id,
            label: field.label || field.string,
            store: field.store,
            type: field.field_type || field.type,
        }));
        if (import_compat) {
            exportedFields.unshift({
                name: "id",
                label: _t("External ID"),
            });
        }
        if (format=='pdf'){
            const resp = await this.rpc("/get_pdf_data", {
                context: this.props.context,
                domain: this.model.root.domain,
                fields: exportedFields,
                groupby: this.model.root.groupBy,
                model: this.model.root.resModel,
                ids:ids
            })
            await this.actionService.doAction({
                type: "ir.actions.report",
                report_type: "qweb-html",
                report_name:"exportpdf.export_pdf",
                report_file: resp.model_description,
                data: {
                    data:resp.data,
                    headers:resp.labels,
                    groupby:this.model.root.groupBy,
                    is_pivot:false,
                    display_name: resp.model_description

                },
                context:{},
                display_name: resp.model_description,
                attachment_use:false
            });
        }
        else{
        await download({
            data: {
                data: JSON.stringify({
                    import_compat,
                    context: this.props.context,
                    domain: this.model.root.domain,
                    fields: exportedFields,
                    groupby: this.model.root.groupBy,
                    ids,
                    model: this.model.root.resModel,
                }),
            },
            url: `/web/export/${format}`,
        });
    }
    }
})