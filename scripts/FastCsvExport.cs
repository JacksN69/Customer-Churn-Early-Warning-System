using System;
using System.IO;
using System.Data;
using System.Text;
using System.Globalization;

public static class FastCsvExport
{
    private static string Cell(object value)
    {
        if (value == null || value == DBNull.Value) return "";
        string s;
        if (value is DateTime) s = ((DateTime)value).ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
        else if (value is IFormattable) s = ((IFormattable)value).ToString(null, CultureInfo.InvariantCulture);
        else s = Convert.ToString(value, CultureInfo.InvariantCulture);
        return "\""+s.Replace("\"","\"\"")+"\"";
    }
    public static long Export(IDataReader reader, string path)
    {
        using (var writer = new StreamWriter(path, false, new UTF8Encoding(false), 131072))
        {
            var names = new string[reader.FieldCount];
            for (int i = 0; i < names.Length; i++) names[i] = Cell(reader.GetName(i));
            writer.WriteLine(string.Join(",",names));
            var cells = new string[reader.FieldCount];
            long rows = 0;
            while (reader.Read())
            {
                for (int i = 0; i < cells.Length; i++)
                    cells[i] = reader.IsDBNull(i) ? "" : Cell(reader.GetValue(i));
                writer.WriteLine(string.Join(",", cells));
                rows++;
            }
            return rows;
        }
    }
}
