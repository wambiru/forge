/*
Sales Tracker - Flutter prototype (lib/main.dart)

This project package contains the app code and dependencies.
After unzipping:

1) Open a terminal in the project folder.
2) Run: flutter create .
   (This generates android/ios folders required to build platform apps)
3) Run: flutter pub get
4) Build the release APK:
   flutter build apk --release
5) The APK will be in build/app/outputs/flutter-apk/app-release.apk

Notes:
- All currency amounts are shown as Ksh in the UI and PDF.
- If you need an APK built for you, I can provide step-by-step guidance.
*/

import 'dart:io';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:sqflite/sqflite.dart';
import 'package:pdf/widgets.dart' as pw;
import 'package:pdf/pdf.dart';
import 'package:printing/printing.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await SalesDatabase.instance.init();
  runApp(MyApp());
}

class MyApp extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Sales Tracker (Ksh)',
      theme: ThemeData(primarySwatch: Colors.blue),
      home: SalesHomePage(),
    );
  }
}

class Sale {
  final int? id;
  final String client;
  final int quantity;
  final double paid;
  final double unpaid;
  final String transactionType; // Mpesa, Cash, Cheque
  final String location;
  final DateTime date;

  Sale({this.id, required this.client, required this.quantity, required this.paid, required this.unpaid, required this.transactionType, required this.location, required this.date});

  double get total => paid + unpaid;

  Map<String, dynamic> toMap() {
    return {
      'id': id,
      'client': client,
      'quantity': quantity,
      'paid': paid,
      'unpaid': unpaid,
      'transactionType': transactionType,
      'location': location,
      'date': date.toIso8601String(),
    };
  }

  static Sale fromMap(Map<String, dynamic> m) {
    return Sale(
      id: m['id'] as int?,
      client: m['client'],
      quantity: m['quantity'],
      paid: m['paid'],
      unpaid: m['unpaid'],
      transactionType: m['transactionType'],
      location: m['location'],
      date: DateTime.parse(m['date']),
    );
  }
}

class SalesDatabase {
  static final SalesDatabase instance = SalesDatabase._init();
  static Database? _database;
  SalesDatabase._init();

  Future<Database> get database async {
    if (_database != null) return _database!;
    _database = await _initDB('sales.db');
    return _database!;
  }

  Future<void> init() async {
    await database;
  }

  Future<Database> _initDB(String fileName) async {
    Directory documentsDirectory = await getApplicationDocumentsDirectory();
    final dbPath = p.join(documentsDirectory.path, fileName);
    return await openDatabase(dbPath, version: 1, onCreate: _createDB);
  }

  Future _createDB(Database db, int version) async {
    await db.execute('''
      CREATE TABLE sales(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client TEXT,
        quantity INTEGER,
        paid REAL,
        unpaid REAL,
        transactionType TEXT,
        location TEXT,
        date TEXT
      )
    ''');
  }

  Future<Sale> create(Sale sale) async {
    final db = await instance.database;
    final id = await db.insert('sales', sale.toMap());
    return Sale(id: id, client: sale.client, quantity: sale.quantity, paid: sale.paid, unpaid: sale.unpaid, transactionType: sale.transactionType, location: sale.location, date: sale.date);
  }

  Future<List<Sale>> readAll({DateTime? from, DateTime? to}) async {
    final db = await instance.database;
    String where = '';
    List<dynamic> args = [];
    if (from != null && to != null) {
      where = 'WHERE date BETWEEN ? AND ?';
      args = [from.toIso8601String(), to.toIso8601String()];
    }
    final result = await db.rawQuery('SELECT * FROM sales $where ORDER BY date DESC', args);
    return result.map((m) => Sale.fromMap(m)).toList();
  }

  Future close() async {
    final db = await instance.database;
    db.close();
  }
}

class SalesHomePage extends StatefulWidget {
  @override
  _SalesHomePageState createState() => _SalesHomePageState();
}

class _SalesHomePageState extends State<SalesHomePage> {
  List<Sale> _sales = [];
  DateTime? _filterFrom;
  DateTime? _filterTo;

  @override
  void initState() {
    super.initState();
    _loadSales();
  }

  Future<void> _loadSales() async {
    final sales = await SalesDatabase.instance.readAll(from: _filterFrom, to: _filterTo);
    setState(() {
      _sales = sales;
    });
  }

  double get totalPaid => _sales.fold(0, (s, e) => s + e.paid);
  double get totalUnpaid => _sales.fold(0, (s, e) => s + e.unpaid);
  double get totalRevenue => _sales.fold(0, (s, e) => s + e.total);

  Future<void> _showAddSale() async {
    final created = await showModalBottomSheet<Sale>(
      context: context,
      isScrollControlled: true,
      builder: (_) => Padding(
        padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
        child: AddSaleForm(),
      ),
    );
    if (created != null) {
      await SalesDatabase.instance.create(created);
      await _loadSales();
    }
  }

  Future<void> _pickDateRange() async {
    final now = DateTime.now();
    final pickedFrom = await showDatePicker(context: context, initialDate: now.subtract(Duration(days: 7)), firstDate: DateTime(2000), lastDate: DateTime(2100));
    if (pickedFrom == null) return;
    final pickedTo = await showDatePicker(context: context, initialDate: now, firstDate: pickedFrom, lastDate: DateTime(2100));
    if (pickedTo == null) return;
    setState(() {
      _filterFrom = pickedFrom;
      _filterTo = pickedTo.add(Duration(hours: 23, minutes: 59, seconds: 59));
    });
    await _loadSales();
  }

  Future<void> _clearFilter() async {
    setState(() {
      _filterFrom = null;
      _filterTo = null;
    });
    await _loadSales();
  }

  Future<void> _generatePdfReport() async {
    final from = _filterFrom ?? DateTime(2000);
    final to = _filterTo ?? DateTime.now();
    final sales = await SalesDatabase.instance.readAll(from: from, to: to);

    final pdf = pw.Document();
    final dateFmt = DateFormat('yyyy-MM-dd HH:mm');

    pdf.addPage(pw.MultiPage(
      build: (pw.Context ctx) => [
        pw.Header(level: 0, child: pw.Text('Sales Report')),
        pw.Text('From: ${DateFormat('yyyy-MM-dd').format(from)}  To: ${DateFormat('yyyy-MM-dd').format(to)}'),
        pw.SizedBox(height: 12),
        pw.Table.fromTextArray(
          headers: ['Date', 'Client', 'Qty', 'Paid', 'Unpaid', 'Total', 'Type', 'Location'],
          data: sales.map((s) => [
            dateFmt.format(s.date),
            s.client,
            s.quantity.toString(),
            'Ksh ${s.paid.toStringAsFixed(2)}',
            'Ksh ${s.unpaid.toStringAsFixed(2)}',
            'Ksh ${s.total.toStringAsFixed(2)}',
            s.transactionType,
            s.location
          ]).toList(),
        ),
        pw.SizedBox(height: 12),
        pw.Text('Totals', style: pw.TextStyle(fontWeight: pw.FontWeight.bold)),
        pw.Text('Paid: Ksh ${sales.fold(0, (p, e) => p + e.paid).toStringAsFixed(2)}'),
        pw.Text('Unpaid: Ksh ${sales.fold(0, (p, e) => p + e.unpaid).toStringAsFixed(2)}'),
        pw.Text('Total: Ksh ${sales.fold(0, (p, e) => p + e.total).toStringAsFixed(2)}'),
      ],
    ));

    final output = await getTemporaryDirectory();
    final file = File(p.join(output.path, 'sales_report_${DateTime.now().millisecondsSinceEpoch}.pdf'));
    await file.writeAsBytes(await pdf.save());

    await Printing.sharePdf(bytes: await pdf.save(), filename: file.path.split('/').last);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Sales Tracker (Ksh)'),
        actions: [
          IconButton(icon: Icon(Icons.date_range), onPressed: _pickDateRange),
          IconButton(icon: Icon(Icons.picture_as_pdf), onPressed: _generatePdfReport),
          IconButton(icon: Icon(Icons.clear), onPressed: _clearFilter),
        ],
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(8.0),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('Paid: Ksh ${totalPaid.toStringAsFixed(2)}'),
                  Text('Unpaid: Ksh ${totalUnpaid.toStringAsFixed(2)}')
                ]),
                Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                  Text('Total: Ksh ${totalRevenue.toStringAsFixed(2)}'),
                  if (_filterFrom != null && _filterTo != null)
                    Text('Filter: ${DateFormat('yyyy-MM-dd').format(_filterFrom!)} - ${DateFormat('yyyy-MM-dd').format(_filterTo!)}')
                ]),
              ],
            ),
          ),
          Expanded(
            child: _sales.isEmpty
                ? Center(child: Text('No sales recorded'))
                : ListView.builder(
                    itemCount: _sales.length,
                    itemBuilder: (context, idx) {
                      final s = _sales[idx];
                      return ListTile(
                        title: Text('${s.client} — ${s.transactionType}'),
                        subtitle: Text('${DateFormat('yyyy-MM-dd').format(s.date)} • ${s.location}'),
                        trailing: Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Text('Paid: Ksh ${s.paid.toStringAsFixed(2)}'),
                              Text('Unpaid: Ksh ${s.unpaid.toStringAsFixed(2)}')
                            ]),
                      );
                    },
                  ),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: _showAddSale,
        child: Icon(Icons.add),
      ),
    );
  }
}

class AddSaleForm extends StatefulWidget {
  @override
  _AddSaleFormState createState() => _AddSaleFormState();
}

class _AddSaleFormState extends State<AddSaleForm> {
  final _formKey = GlobalKey<FormState>();
  final _clientCtrl = TextEditingController();
  final _quantityCtrl = TextEditingController();
  final _paidCtrl = TextEditingController();
  final _unpaidCtrl = TextEditingController();
  final _locationCtrl = TextEditingController();
  String _transactionType = 'Mpesa';
  DateTime _date = DateTime.now();

  @override
  void dispose() {
    _clientCtrl.dispose();
    _quantityCtrl.dispose();
    _paidCtrl.dispose();
    _unpaidCtrl.dispose();
    _locationCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    final sale = Sale(
      client: _clientCtrl.text.trim(),
      quantity: int.tryParse(_quantityCtrl.text.trim()) ?? 0,
      paid: double.tryParse(_paidCtrl.text.trim()) ?? 0.0,
      unpaid: double.tryParse(_unpaidCtrl.text.trim()) ?? 0.0,
      transactionType: _transactionType,
      location: _locationCtrl.text.trim(),
      date: _date,
    );
    Navigator.of(context).pop(sale);
  }

  Future<void> _pickDate() async {
    final picked = await showDatePicker(context: context, initialDate: _date, firstDate: DateTime(2000), lastDate: DateTime(2100));
    if (picked != null) setState(() => _date = picked);
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(16.0),
      child: SingleChildScrollView(
        child: Form(
          key: _formKey,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text('Add Sale', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
              SizedBox(height: 8),
              TextFormField(controller: _clientCtrl, decoration: InputDecoration(labelText: 'Client name'), validator: (v) => v == null || v.trim().isEmpty ? 'Required' : null),
              TextFormField(controller: _quantityCtrl, decoration: InputDecoration(labelText: 'Quantity'), keyboardType: TextInputType.number, validator: (v) => v == null || v.trim().isEmpty ? 'Required' : null),
              Row(children: [
                Expanded(child: TextFormField(controller: _paidCtrl, decoration: InputDecoration(labelText: 'Paid amount (Ksh)'), keyboardType: TextInputType.number)),
                SizedBox(width: 8),
                Expanded(child: TextFormField(controller: _unpaidCtrl, decoration: InputDecoration(labelText: 'Unpaid amount (Ksh)'), keyboardType: TextInputType.number))
              ]),
              SizedBox(height: 8),
              DropdownButtonFormField<String>(value: _transactionType, items: ['Mpesa', 'Cash', 'Cheque'].map((t) => DropdownMenuItem(value: t, child: Text(t))).toList(), onChanged: (v) => setState(() => _transactionType = v ?? 'Mpesa'), decoration: InputDecoration(labelText: 'Transaction type')),
              TextFormField(controller: _locationCtrl, decoration: InputDecoration(labelText: 'Client location (manual entry)'), validator: (v) => v == null || v.trim().isEmpty ? 'Required' : null),
              SizedBox(height: 8),
              Row(children: [Text('Date: ${DateFormat('yyyy-MM-dd').format(_date)}'), Spacer(), TextButton(onPressed: _pickDate, child: Text('Change'))]),
              SizedBox(height: 12),
              ElevatedButton(onPressed: _submit, child: Text('Save')),
            ],
          ),
        ),
      ),
    );
  }
}
