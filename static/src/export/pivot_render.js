/** @odoo-module */

import {PivotRenderer} from '@web/views/pivot/pivot_renderer';
import {patch} from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";

patch(PivotRenderer.prototype,{
    setup(){
        super.setup();
        this.rpc = useService("rpc");
    },
    async onDownloadButtonClickedPdf() {
        if (this.model.getTableWidth() > 10) {
            throw new Error(
                _t(
                    "For Pdf compatibility, data cannot be exported if there are more than 10 columns.\n\nTip: try to flip axis, filter further or reduce the number of measures."
                )
            );
        }
        const table = this.model.exportData();
        console.log(table)
        await this.actionService.doAction({
            type: "ir.actions.report",
            report_type: "qweb-html",
            report_name:"exportpdf.export_pdf",
            report_file:"exportpdf.export_pdf",
            data: {
                data:JSON.stringify(table),
                is_pivot:true,
            },
            context:{},
            display_name: "renderpivot",
            attachment_use:false
        });
       
    }

})