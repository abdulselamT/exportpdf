import datetime
import functools
import io
import itertools
import json
import logging
import operator
from odoo import http
from odoo.http import content_disposition, request
from odoo.addons.web.controllers.export import Export
from odoo.tools.translate import _
from collections import deque
from odoo.tools import ustr, osutil

from odoo.tools.misc import xlsxwriter
from odoo.tools import lazy_property, osutil, pycompat
from collections import OrderedDict
_logger = logging.getLogger(__name__)

def none_values_filtered(func):
    @functools.wraps(func)
    def wrap(iterable):
        return func(v for v in iterable if v is not None)
    return wrap

def allow_empty_iterable(func):
    """
    Some functions do not accept empty iterables (e.g. max, min with no default value)
    This returns the function `func` such that it returns None if the iterable
    is empty instead of raising a ValueError.
    """
    @functools.wraps(func)
    def wrap(iterable):
        iterator = iter(iterable)
        try:
            value = next(iterator)
            return func(itertools.chain([value], iterator))
        except StopIteration:
            return None
    return wrap

OPERATOR_MAPPING = {
    'max': none_values_filtered(allow_empty_iterable(max)),
    'min': none_values_filtered(allow_empty_iterable(min)),
    'sum': sum,
    'bool_and': all,
    'bool_or': any,
}

class GroupsTreeNode:
    """
    This class builds an ordered tree of groups from the result of a `read_group(lazy=False)`.
    The `read_group` returns a list of dictionnaries and each dictionnary is used to
    build a leaf. The entire tree is built by inserting all leaves.
    """

    def __init__(self, model, fields, groupby, groupby_type, root=None):
        self._model = model
        self._export_field_names = fields  # exported field names (e.g. 'journal_id', 'account_id/name', ...)
        self._groupby = groupby
        self._groupby_type = groupby_type

        self.count = 0  # Total number of records in the subtree
        self.children = OrderedDict()
        self.data = []  # Only leaf nodes have data
        if root:
            self.insert_leaf(root)

    def _get_aggregate(self, field_name, data, group_operator):
        # When exporting one2many fields, multiple data lines might be exported for one record.
        # Blank cells of additionnal lines are filled with an empty string. This could lead to '' being
        # aggregated with an integer or float.
        data = (value for value in data if value != '')

        if group_operator == 'avg':
            return self._get_avg_aggregate(field_name, data)

        aggregate_func = OPERATOR_MAPPING.get(group_operator)
        if not aggregate_func:
            _logger.warning("Unsupported export of group_operator '%s' for field %s on model %s", group_operator, field_name, self._model._name)
            return

        if self.data:
            return aggregate_func(data)
        return aggregate_func((child.aggregated_values.get(field_name) for child in self.children.values()))

    def _get_avg_aggregate(self, field_name, data):
        aggregate_func = OPERATOR_MAPPING.get('sum')
        if self.data:
            return aggregate_func(data) / self.count
        children_sums = (child.aggregated_values.get(field_name) * child.count for child in self.children.values())
        return aggregate_func(children_sums) / self.count

    def _get_aggregated_field_names(self):
        """ Return field names of exported field having a group operator """
        aggregated_field_names = []
        for field_name in self._export_field_names:
            if field_name == '.id':
                field_name = 'id'
            if '/' in field_name:
                # Currently no support of aggregated value for nested record fields
                # e.g. line_ids/analytic_line_ids/amount
                continue
            field = self._model._fields[field_name]
            if field.group_operator:
                aggregated_field_names.append(field_name)
        return aggregated_field_names

    # Lazy property to memoize aggregated values of children nodes to avoid useless recomputations
    @lazy_property
    def aggregated_values(self):

        aggregated_values = {}

        # Transpose the data matrix to group all values of each field in one iterable
        field_values = zip(*self.data)
        for field_name in self._export_field_names:
            field_data = self.data and next(field_values) or []

            if field_name in self._get_aggregated_field_names():
                field = self._model._fields[field_name]
                aggregated_values[field_name] = self._get_aggregate(field_name, field_data, field.group_operator)

        return aggregated_values

    def child(self, key):
        """
        Return the child identified by `key`.
        If it doesn't exists inserts a default node and returns it.
        :param key: child key identifier (groupby value as returned by read_group,
                    usually (id, display_name))
        :return: the child node
        """
        if key not in self.children:
            self.children[key] = GroupsTreeNode(self._model, self._export_field_names, self._groupby, self._groupby_type)
        return self.children[key]

    def insert_leaf(self, group):
        """
        Build a leaf from `group` and insert it in the tree.
        :param group: dict as returned by `read_group(lazy=False)`
        """
        leaf_path = [group.get(groupby_field) for groupby_field in self._groupby]
        domain = group.pop('__domain')
        count = group.pop('__count')

        records = self._model.search(domain, offset=0, limit=False, order=False)

        # Follow the path from the top level group to the deepest
        # group which actually contains the records' data.
        node = self # root
        node.count += count
        for node_key in leaf_path:
            # Go down to the next node or create one if it does not exist yet.
            node = node.child(node_key)
            # Update count value and aggregated value.
            node.count += count

        node.data = records.export_data(self._export_field_names).get('datas', [])
   


class ExportPdf(http.Controller):    
    @http.route('/get_pdf_data', type='json', auth="user")
    def get_pdf_data(self, **kw):
        self.data_list=[]
        Model = request.env[kw['model']].with_context(kw.get('context', {}))
        domain=kw['domain']     
        fields=kw['fields']
        ids=kw.get('ids',False)
        domain=[("id","in",ids)] if ids else domain
        labels=[field.get('string') or field.get("label") for field in fields]
        if not Model._is_an_ordinary_table():
            field_names = [field for field in fields if field['name'] != 'id']
        field_names=[field.get('name') for field in fields]
        records = Model.search(domain, offset=0, limit=False, order=False)
        export_data = records.export_data(field_names).get('datas', [])
        model_description = request.env['ir.model']._get(kw['model']).name
        groupby=kw.get('groupby')
        if groupby:
            field_names=groupby+[field.get('name') for field in fields if field.get('name') not in groupby]
            labels=field_names
            self.fields=[field for field in fields if  field.get('name')  not in groupby]
            export_data=self.base(Model=Model,ids=ids,field_names=field_names,groupby=groupby,fields=fields,domain=domain)
        return {
            "labels":labels,
            "data":export_data,
            "model_description":model_description,
        }
    def write_group(self, row, column, group_name, group, group_depth=0):
        group_name = group_name[1] if isinstance(group_name, tuple) and len(group_name) > 1 else group_name
        if group._groupby_type[group_depth] != 'boolean':
            group_name = group_name or _("Undefined")
        row, column = self._write_group_header(row, column, group_name, group, group_depth)

        # Recursively write sub-groups
        for child_group_name, child_group in group.children.items():
            row, column = self.write_group(row, column, child_group_name, child_group, group_depth + 1)
        for record in group.data:
            row, column = self._write_row(row, column, record)
        return row, column

    def _write_row(self, row, column, data):
        data=data
        self.data_list.append(data)
        for value in data:
            #self.write_cell(row, column, value)
            column += 1
        return row + 1, 0

    def _write_group_header(self, row, column, label, group, group_depth=0):
        aggregates = group.aggregated_values
        label = '%s (%s)' % (label, group.count)
        self.data_list.append(["group_by",label,group_depth])
        #self.write(row, column, label, self.header_bold_style)
        for field in self.fields[1:]: # No aggregates allowed in the first column because of the group title
            column += 1
            aggregated_value = aggregates.get(field['name'])
            if field.get('type') == 'monetary':
                continue
                self.header_bold_style.set_num_format(self.monetary_format)
            elif field.get('type') == 'float':
                continue
                self.header_bold_style.set_num_format(self.float_format)
            else:
                aggregated_value = str(aggregated_value if aggregated_value is not None else '')
            #self.write(row, column, aggregated_value, self.header_bold_style)
        return row + 1, 0


    def from_group_data(self, fields, groups):
        x, y = 1, 0
        for group_name, group in groups.children.items():
            x, y = self.write_group(x, y, group_name, group)
        return []
    

    def base(self,Model,ids,field_names,groupby,fields,domain,counter=-1,l=[],categ="",started=0):
        groupby_type = [Model._fields[x.split(':')[0]].type for x in groupby]
        domain = [('id', 'in', ids)] if ids else domain
        groups_data = Model.with_context(active_test =False).read_group(domain, ['__count'], groupby, lazy=False)
        tree = GroupsTreeNode(Model, field_names, groupby, groupby_type)
        for leaf in groups_data:
            tree.insert_leaf(leaf)
        response_data = self.from_group_data(fields, tree)
        new_list=[]
        field_len=len(fields)
        for data in self.data_list:
           if data[0]=="group_by":
               x=[False]*field_len
               x[data[-1]]=f"<strong>{data[1]}</strong>"
               new_list.append(x)
           else:
                data=[False]*len(groupby)+data[len(groupby):]
                new_list.append(data)
        return new_list
           



           
class ExportPdfAdd(Export):
    @http.route('/web/export/formats', type='json', auth="user")
    def formats(self):
        """ Returns all valid export formats

        :returns: for each export format, a pair of identifier and printable name
        :rtype: [(str, str)]
        """
        return [
            {'tag': 'xlsx', 'label': 'XLSX', 'error': None if xlsxwriter else "XlsxWriter 0.9.3 required"},
            {'tag': 'csv', 'label': 'CSV'},
            {'tag':'pdf','label':"PDF"}
        ]